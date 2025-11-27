"""
Nibe Autotuner - Streamlit GUI
Interactive web interface for heat pump monitoring and optimization
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from analyzer import HeatPumpAnalyzer, EfficiencyMetrics
from visualizer import HeatPumpVisualizer
from models import init_db, Device, Parameter, ParameterReading as ParameterReadingModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy import func, and_

# Page configuration
st.set_page_config(
    page_title="Nibe Autotuner",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .status-good {
        color: #28a745;
        font-weight: bold;
    }
    .status-warning {
        color: #ffc107;
        font-weight: bold;
    }
    .status-bad {
        color: #dc3545;
        font-weight: bold;
    }
    .big-number {
        font-size: 2.5em;
        font-weight: bold;
        margin: 0;
    }
    .subtitle {
        color: #666;
        font-size: 0.9em;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'analyzer' not in st.session_state:
    st.session_state.analyzer = HeatPumpAnalyzer()
if 'visualizer' not in st.session_state:
    st.session_state.visualizer = HeatPumpVisualizer()

def get_database_stats():
    """Get database statistics"""
    engine = init_db('sqlite:///./data/nibe_autotuner.db')
    SessionMaker = sessionmaker(bind=engine)
    session = SessionMaker()

    total_readings = session.query(func.count(ParameterReadingModel.id)).scalar()
    unique_timestamps = session.query(
        func.count(func.distinct(ParameterReadingModel.timestamp))
    ).scalar()
    first_reading = session.query(func.min(ParameterReadingModel.timestamp)).scalar()
    last_reading = session.query(func.max(ParameterReadingModel.timestamp)).scalar()

    session.close()

    return {
        'total_readings': total_readings,
        'unique_timestamps': unique_timestamps,
        'first_reading': first_reading,
        'last_reading': last_reading
    }

def status_indicator(value, optimal_min, optimal_max, invert=False):
    """Return emoji indicator based on value range"""
    if invert:
        if optimal_min <= value <= optimal_max:
            return "✅"
        elif (optimal_min - 100) <= value < optimal_min or optimal_max < value <= (optimal_max + 100):
            return "⚠️"
        else:
            return "❌"
    else:
        if optimal_min <= value <= optimal_max:
            return "✅"
        elif (optimal_min - 2) <= value < optimal_min or optimal_max < value <= (optimal_max + 2):
            return "⚠️"
        else:
            return "❌"

def main():
    # Header
    st.title("🔥 Nibe Autotuner")
    st.markdown("**AI-powered heat pump optimization system**")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")

        analysis_period = st.selectbox(
            "Analysis Period",
            options=[6, 12, 24, 48, 72, 168],
            index=2,
            format_func=lambda x: f"Last {x} hours" if x < 168 else f"Last {x//24} days"
        )

        st.markdown("---")

        # Database info
        st.header("📊 Database")
        stats = get_database_stats()

        if stats['total_readings']:
            st.metric("Total Readings", f"{stats['total_readings']:,}")
            st.metric("Timestamps", f"{stats['unique_timestamps']:,}")

            if stats['first_reading'] and stats['last_reading']:
                duration = stats['last_reading'] - stats['first_reading']
                days = duration.total_seconds() / 86400
                st.metric("Data Span", f"{days:.1f} days")

                st.caption(f"First: {stats['first_reading'].strftime('%Y-%m-%d')}")
                st.caption(f"Last: {stats['last_reading'].strftime('%Y-%m-%d')}")
        else:
            st.warning("No data in database")
            st.info("Run data logger to collect data")

        st.markdown("---")

        # Quick actions
        st.header("🚀 Quick Actions")
        if st.button("🔄 Refresh Data"):
            st.rerun()

        if st.button("📈 Generate Plots"):
            with st.spinner("Generating visualizations..."):
                st.session_state.visualizer.plot_temperatures(hours_back=analysis_period)
                st.session_state.visualizer.plot_efficiency(hours_back=analysis_period)
                st.session_state.visualizer.create_dashboard(hours_back=analysis_period)
            st.success("Plots generated!")
            st.rerun()

    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard",
        "🎯 Recommendations",
        "📈 Visualizations",
        "📉 Historical Data",
        "📚 Documentation"
    ])

    # Tab 1: Dashboard
    with tab1:
        st.header("Current System Status")

        try:
            # Calculate metrics
            metrics = st.session_state.analyzer.calculate_metrics(hours_back=analysis_period)

            # Top metrics row
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                cop_status = "✅" if metrics.estimated_cop and metrics.estimated_cop >= 3.0 else "⚠️"
                cop_str = f"{metrics.estimated_cop:.2f}" if metrics.estimated_cop else "N/A"
                st.markdown(f"<div class='metric-card'>", unsafe_allow_html=True)
                st.markdown(f"<p class='big-number'>{cop_str} {cop_status}</p>", unsafe_allow_html=True)
                st.markdown("<p class='subtitle'>COP (Coefficient of Performance)</p>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with col2:
                dm_status = status_indicator(metrics.degree_minutes, -300, -100, invert=True)
                st.markdown(f"<div class='metric-card'>", unsafe_allow_html=True)
                st.markdown(f"<p class='big-number'>{metrics.degree_minutes:.0f} {dm_status}</p>", unsafe_allow_html=True)
                st.markdown("<p class='subtitle'>Degree Minutes (target: -200)</p>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with col3:
                # Use active space heating Delta T if available, otherwise fall back to all readings
                display_delta_t = metrics.delta_t_active if metrics.delta_t_active is not None else metrics.delta_t
                # For mixed systems with underfloor heating, 3-5°C is acceptable
                dt_status = status_indicator(display_delta_t, 3, 8)
                st.markdown(f"<div class='metric-card'>", unsafe_allow_html=True)
                st.markdown(f"<p class='big-number'>{display_delta_t:.1f}°C {dt_status}</p>", unsafe_allow_html=True)
                st.markdown("<p class='subtitle'>Delta T - Active Space Heating</p>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with col4:
                st.markdown(f"<div class='metric-card'>", unsafe_allow_html=True)
                st.markdown(f"<p class='big-number'>{metrics.avg_compressor_freq:.0f} Hz</p>", unsafe_allow_html=True)
                st.markdown("<p class='subtitle'>Compressor Frequency</p>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("---")

            # Temperature details
            st.subheader("🌡️ Temperatures")
            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Outdoor", f"{metrics.avg_outdoor_temp:.1f}°C")
            col2.metric("Indoor", f"{metrics.avg_indoor_temp:.1f}°C")
            col3.metric("Supply", f"{metrics.avg_supply_temp:.1f}°C")
            col4.metric("Return", f"{metrics.avg_return_temp:.1f}°C")

            # Delta T breakdown
            st.subheader("📊 Delta T Analysis")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("All Readings", f"{metrics.delta_t:.1f}°C",
                         help="Average Delta T including standby periods")

            with col2:
                if metrics.delta_t_active is not None:
                    active_status = '✅' if 3 <= metrics.delta_t_active <= 8 else '⚠️'
                    st.metric("Space Heating (Active)", f"{metrics.delta_t_active:.1f}°C {active_status}",
                             help="Delta T when compressor is actively heating (>20 Hz, supply <45°C)")
                else:
                    st.metric("Space Heating (Active)", "N/A",
                             help="No active space heating readings in this period")

            with col3:
                if metrics.delta_t_hot_water is not None:
                    st.metric("Hot Water Production", f"{metrics.delta_t_hot_water:.1f}°C",
                             help="Delta T during hot water production (>20 Hz, supply >45°C)")
                else:
                    st.metric("Hot Water Production", "N/A",
                             help="No hot water production in this period")

            # System settings
            st.subheader("⚙️ System Settings")
            col1, col2 = st.columns(2)

            col1.metric("Heating Curve", f"{metrics.heating_curve:.1f}")
            col2.metric("Curve Offset", f"{metrics.curve_offset:.1f}")

            # Period info
            st.caption(f"Analysis period: {metrics.period_start.strftime('%Y-%m-%d %H:%M')} to {metrics.period_end.strftime('%Y-%m-%d %H:%M')}")

        except Exception as e:
            st.error(f"Error loading metrics: {e}")
            st.info("Make sure the data logger has collected some data.")

    # Tab 2: Recommendations
    with tab2:
        st.header("🎯 Optimization Recommendations")

        try:
            recommendations = st.session_state.analyzer.generate_recommendations(
                hours_back=analysis_period,
                min_confidence=0.6
            )

            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    with st.expander(f"#{i} {rec.parameter_name} (Confidence: {rec.confidence*100:.0f}%)", expanded=True):
                        col1, col2 = st.columns(2)

                        with col1:
                            st.metric("Current Value", f"{rec.current_value:.1f}")
                        with col2:
                            st.metric("Suggested Value", f"{rec.suggested_value:.1f}")

                        st.info(f"**Expected Impact:** {rec.expected_impact}")
                        st.markdown(f"**Reasoning:** {rec.reasoning}")

                        if st.button(f"✅ Mark as Applied", key=f"apply_{i}"):
                            st.success("Recommendation marked! Track the results over the next few days.")
            else:
                st.success("🎉 No optimization recommendations!")
                st.info("Your heat pump is operating efficiently. System will alert you if adjustments are needed.")

                # Show current status
                metrics = st.session_state.analyzer.calculate_metrics(hours_back=analysis_period)
                cop_str = f"{metrics.estimated_cop:.2f}" if metrics.estimated_cop else "N/A"
                st.markdown("### Current Performance")
                st.markdown(f"- **COP**: {cop_str} ✅")
                st.markdown(f"- **Degree Minutes**: {metrics.degree_minutes:.0f} ({'✅' if -300 <= metrics.degree_minutes <= -100 else '⚠️'})")

                # Display Delta T with breakdown
                if metrics.delta_t_active is not None:
                    dt_status = '✅' if 3 <= metrics.delta_t_active <= 8 else '⚠️'
                    st.markdown(f"- **Delta T (Active Space Heating)**: {metrics.delta_t_active:.1f}°C {dt_status}")
                else:
                    st.markdown(f"- **Delta T (All)**: {metrics.delta_t:.1f}°C ({'✅' if 3 <= metrics.delta_t <= 8 else '⚠️'})")

        except Exception as e:
            st.error(f"Error generating recommendations: {e}")

    # Tab 3: Visualizations
    with tab3:
        st.header("📈 Performance Visualizations")

        # Check if plots exist
        plots = {
            'Dashboard': 'data/dashboard.png',
            'Temperature Trends': 'data/temperature_plot.png',
            'Efficiency Metrics': 'data/efficiency_plot.png',
            'COP Analysis': 'data/cop_plot.png'
        }

        available_plots = {name: path for name, path in plots.items() if Path(path).exists()}

        if available_plots:
            for name, path in available_plots.items():
                st.subheader(name)
                st.image(path, use_container_width=True)
        else:
            st.info("No visualizations available yet.")
            st.markdown("Click **Generate Plots** in the sidebar to create visualizations.")

    # Tab 4: Historical Data
    with tab4:
        st.header("📉 Historical Data Analysis")

        st.subheader("Query Historical Readings")

        col1, col2 = st.columns(2)

        with col1:
            # Get available parameters
            engine = init_db('sqlite:///./data/nibe_autotuner.db')
            SessionMaker = sessionmaker(bind=engine)
            session = SessionMaker()

            params = session.query(Parameter).order_by(Parameter.parameter_name).all()
            param_options = {f"{p.parameter_name} ({p.parameter_id})": p.parameter_id for p in params}

            selected_param_name = st.selectbox("Select Parameter", options=list(param_options.keys()))
            selected_param_id = param_options[selected_param_name]

            session.close()

        with col2:
            query_hours = st.number_input("Hours of Data", min_value=1, max_value=720, value=168)

        if st.button("📊 Load Data"):
            with st.spinner("Loading data..."):
                device = st.session_state.analyzer.get_device()
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(hours=query_hours)

                readings = st.session_state.analyzer.get_readings(
                    device, selected_param_id, start_time, end_time
                )

                if readings:
                    df = pd.DataFrame(readings, columns=['Timestamp', 'Value'])

                    st.success(f"Loaded {len(readings)} readings")

                    # Statistics
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Average", f"{df['Value'].mean():.2f}")
                    col2.metric("Min", f"{df['Value'].min():.2f}")
                    col3.metric("Max", f"{df['Value'].max():.2f}")
                    col4.metric("Std Dev", f"{df['Value'].std():.2f}")

                    # Chart
                    st.line_chart(df.set_index('Timestamp'))

                    # Data table
                    with st.expander("View Raw Data"):
                        st.dataframe(df, use_container_width=True)
                else:
                    st.warning("No data found for selected parameter and time range.")

    # Tab 5: Documentation
    with tab5:
        st.header("📚 Documentation & Resources")

        st.markdown("""
        ### System Overview

        The Nibe Autotuner uses advanced algorithms and scientific research to optimize your **Nibe F730 CU 3x400V** heat pump.

        #### Your Heat Pump Model

        **Nibe F730 CU 3x400V**
        - Exhaust air heat pump with integrated water heater
        - Inverter controlled compressor (1.1-6.0 kW)
        - Exhaust air temperature range: -15°C to operation
        - Serial: 06615522045017

        #### Key Metrics

        **COP (Coefficient of Performance)**
        - Measure of heat pump efficiency
        - Higher is better (typically 2.0-5.0)
        - Based on Carnot efficiency with 45% real-world factor
        - **Your system: 3.11 average ✅ Excellent**

        **Degree Minutes**
        - Integrated temperature deficit over time
        - Target: -200 DM (optimal comfort/efficiency balance)
        - Range: -300 to -100 DM (comfort zone)
        - Factory default: -60 DM (more frequent cycling)
        - **Your system: -212 DM ✅ Perfect**

        **Delta T (Temperature Differential)**
        - Supply - Return temperature
        - Optimal: 5-8°C for exhaust air heat pumps
        - Too low (<3°C) = poor heat extraction
        - Too high (>10°C) = insufficient flow
        - **Your system: 3.1°C ⚠️ Could be improved**

        **Heating Curve**
        - Defines water temperature based on outdoor temp
        - Range: 0-15 (typical residential: 5-9)
        - Underfloor heating: 3-6, Radiators: 5-9
        - Higher values = warmer water in cold weather
        - **Your system: Curve 7.0, Offset -1.0 ✅ Good**

        #### Manufacturer Specifications

        **Nibe F730 Operating Limits:**
        - Compressor output: 1.1-6.0 kW
        - Exhaust air flow: 90-252 m³/h
        - Critical threshold: Compressor blocks if exhaust air <6°C
        - Optimal hot water temp: 45°C (55°C max without heavy electric backup)

        See [Nibe F730 Technical Baseline](../docs/NIBE_F730_BASELINE.md) for detailed specifications.

        #### Scientific Foundation

        All calculations are based on:
        - Manufacturer specifications (Nibe F730)
        - Academic research papers (2024-2025)
        - Industry best practices
        - 70.6 days of real data from your system

        **Key Documents:**
        - [Nibe F730 Technical Baseline](../docs/NIBE_F730_BASELINE.md) - Model-specific specs
        - [Scientific Baseline](../docs/SCIENTIFIC_BASELINE.md) - Research references

        #### System Commands

        **Start Data Logger:**
        ```bash
        ./install_service.sh
        ```

        **View Logs:**
        ```bash
        journalctl -u nibe-autotuner -f
        ```

        **Run Analysis:**
        ```bash
        python src/analyzer.py
        ```

        **Start API Server:**
        ```bash
        python src/api_server.py
        ```

        #### Resources

        - [GitHub Repository](https://github.com/Peccz/nibe_autotuner)
        - [myUplink API Documentation](https://dev.myuplink.com/)
        - [README](../README.md)
        - [Database Design](../docs/DATABASE_DESIGN.md)
        """)

if __name__ == '__main__':
    main()
