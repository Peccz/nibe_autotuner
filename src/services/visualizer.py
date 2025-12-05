"""
Data visualization module for heat pump metrics
Creates graphs and charts for analysis
"""
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from loguru import logger

from services.analyzer import HeatPumpAnalyzer


class HeatPumpVisualizer:
    """Generate visualizations of heat pump performance"""

    def __init__(self, analyzer: Optional[HeatPumpAnalyzer] = None):
        """Initialize visualizer"""
        self.analyzer = analyzer or HeatPumpAnalyzer()

    def plot_temperatures(
        self,
        hours_back: int = 24,
        output_file: str = 'data/temperature_plot.png'
    ) -> str:
        """
        Plot temperature trends over time

        Args:
            hours_back: Number of hours to plot
            output_file: Path to save the plot

        Returns:
            Path to the generated plot file
        """
        device = self.analyzer.get_device()
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        # Fetch temperature data
        outdoor = self.analyzer.get_readings(
            device, self.analyzer.PARAM_OUTDOOR_TEMP, start_time, end_time
        )
        indoor = self.analyzer.get_readings(
            device, self.analyzer.PARAM_INDOOR_TEMP, start_time, end_time
        )
        supply = self.analyzer.get_readings(
            device, self.analyzer.PARAM_SUPPLY_TEMP, start_time, end_time
        )
        return_temp = self.analyzer.get_readings(
            device, self.analyzer.PARAM_RETURN_TEMP, start_time, end_time
        )

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 8))

        # Plot data
        if outdoor:
            times, values = zip(*outdoor)
            ax.plot(times, values, label='Outdoor', linewidth=2, color='blue')

        if indoor:
            times, values = zip(*indoor)
            ax.plot(times, values, label='Indoor', linewidth=2, color='green')

        if supply:
            times, values = zip(*supply)
            ax.plot(times, values, label='Supply', linewidth=2, color='red')

        if return_temp:
            times, values = zip(*return_temp)
            ax.plot(times, values, label='Return', linewidth=2, color='orange')

        # Formatting
        ax.set_xlabel('Time', fontsize=12)
        ax.set_ylabel('Temperature (°C)', fontsize=12)
        ax.set_title(f'Heat Pump Temperatures - Last {hours_back} Hours', fontsize=14, fontweight='bold')
        ax.legend(loc='best', fontsize=10)
        ax.grid(True, alpha=0.3)

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"Temperature plot saved to {output_file}")
        return output_file

    def plot_efficiency(
        self,
        hours_back: int = 24,
        output_file: str = 'data/efficiency_plot.png'
    ) -> str:
        """
        Plot efficiency metrics over time

        Args:
            hours_back: Number of hours to plot
            output_file: Path to save the plot

        Returns:
            Path to the generated plot file
        """
        device = self.analyzer.get_device()
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        # Fetch data
        compressor = self.analyzer.get_readings(
            device, self.analyzer.PARAM_COMPRESSOR_FREQ, start_time, end_time
        )
        degree_mins = self.analyzer.get_readings(
            device, self.analyzer.PARAM_DM_CURRENT, start_time, end_time
        )

        # Create figure with subplots
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Plot compressor frequency
        if compressor:
            times, values = zip(*compressor)
            ax1.plot(times, values, label='Compressor Frequency', linewidth=2, color='purple')
            ax1.fill_between(times, values, alpha=0.3, color='purple')

        ax1.set_ylabel('Frequency (Hz)', fontsize=12)
        ax1.set_title('Compressor Operation', fontsize=12, fontweight='bold')
        ax1.legend(loc='best')
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax1.xaxis.set_major_locator(mdates.HourLocator(interval=2))

        # Plot degree minutes
        if degree_mins:
            times, values = zip(*degree_mins)
            ax2.plot(times, values, label='Degree Minutes', linewidth=2, color='teal')

            # Add target line (manufacturer spec)
            ax2.axhline(
                y=self.analyzer.TARGET_DM,
                color='green',
                linestyle='--',
                linewidth=2,
                label=f'Target ({self.analyzer.TARGET_DM} DM)',
                alpha=0.7
            )

            # Add comfort zones (manufacturer spec)
            ax2.axhspan(
                self.analyzer.TARGET_DM_MIN,
                self.analyzer.TARGET_DM_MAX,
                alpha=0.1,
                color='green',
                label='Comfort Zone (F730 spec)'
            )
            ax2.axhspan(-500, self.analyzer.TARGET_DM_MIN, alpha=0.1, color='yellow')
            ax2.axhspan(self.analyzer.TARGET_DM_MAX, 100, alpha=0.1, color='yellow')

        ax2.set_xlabel('Time', fontsize=12)
        ax2.set_ylabel('Degree Minutes', fontsize=12)
        ax2.set_title('Heating Balance (Degree Minutes)', fontsize=12, fontweight='bold')
        ax2.legend(loc='best')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"Efficiency plot saved to {output_file}")
        return output_file

    def plot_cop_estimate(
        self,
        hours_back: int = 168,  # 7 days
        sample_interval: int = 2,  # Calculate COP every 2 hours
        output_file: str = 'data/cop_plot.png'
    ) -> str:
        """
        Plot estimated COP over time

        Args:
            hours_back: Number of hours to analyze
            sample_interval: Hours between COP calculations
            output_file: Path to save the plot

        Returns:
            Path to the generated plot file
        """
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        timestamps = []
        cop_values = []
        outdoor_temps = []

        # Calculate COP for each interval
        current_time = start_time
        while current_time < end_time:
            interval_end = current_time + timedelta(hours=sample_interval)

            device = self.analyzer.get_device()

            # Get average temperatures for this interval
            outdoor = self.analyzer.calculate_average(
                device, self.analyzer.PARAM_OUTDOOR_TEMP, current_time, interval_end
            )
            supply = self.analyzer.calculate_average(
                device, self.analyzer.PARAM_SUPPLY_TEMP, current_time, interval_end
            )
            return_temp = self.analyzer.calculate_average(
                device, self.analyzer.PARAM_RETURN_TEMP, current_time, interval_end
            )

            if all([outdoor, supply, return_temp]):
                cop = self.analyzer._estimate_cop(outdoor, supply, return_temp)
                if cop:
                    timestamps.append(interval_end)
                    cop_values.append(cop)
                    outdoor_temps.append(outdoor)

            current_time = interval_end

        if not timestamps:
            logger.warning("No data available for COP plot")
            # Create empty plot with message
            fig, ax = plt.subplots(figsize=(14, 6))
            ax.text(0.5, 0.5, 'Insufficient data for COP analysis\nCollect more data to see trends',
                   ha='center', va='center', fontsize=14, transform=ax.transAxes)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            plt.close()
            return output_file

        # Create figure with two y-axes
        fig, ax1 = plt.subplots(figsize=(14, 6))

        # Plot COP
        color = 'tab:blue'
        ax1.set_xlabel('Time', fontsize=12)
        ax1.set_ylabel('COP (Coefficient of Performance)', fontsize=12, color=color)
        ax1.plot(timestamps, cop_values, color=color, linewidth=2, marker='o', markersize=4)
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, alpha=0.3)

        # Add COP reference lines (manufacturer spec)
        ax1.axhline(
            y=self.analyzer.TARGET_COP_MIN,
            color='green',
            linestyle='--',
            alpha=0.5,
            label=f'F730 Target (>={self.analyzer.TARGET_COP_MIN})'
        )
        ax1.axhline(y=2.5, color='orange', linestyle='--', alpha=0.5, label='Fair (2.5)')

        # Plot outdoor temperature on secondary axis
        ax2 = ax1.twinx()
        color = 'tab:red'
        ax2.set_ylabel('Outdoor Temperature (°C)', fontsize=12, color=color)
        ax2.plot(timestamps, outdoor_temps, color=color, linewidth=2, alpha=0.6, linestyle='--')
        ax2.tick_params(axis='y', labelcolor=color)

        # Formatting
        ax1.set_title(f'Heat Pump Efficiency (COP) vs Outdoor Temperature', fontsize=14, fontweight='bold')
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        ax1.legend(loc='upper left')
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"COP plot saved to {output_file}")
        return output_file

    def create_dashboard(
        self,
        hours_back: int = 24,
        output_file: str = 'data/dashboard.png'
    ) -> str:
        """
        Create a comprehensive dashboard with multiple metrics

        Args:
            hours_back: Number of hours to display
            output_file: Path to save the dashboard

        Returns:
            Path to the generated dashboard file
        """
        device = self.analyzer.get_device()
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)

        # Calculate current metrics
        metrics = self.analyzer.calculate_metrics(hours_back=hours_back)

        # Fetch data
        outdoor = self.analyzer.get_readings(
            device, self.analyzer.PARAM_OUTDOOR_TEMP, start_time, end_time
        )
        supply = self.analyzer.get_readings(
            device, self.analyzer.PARAM_SUPPLY_TEMP, start_time, end_time
        )
        return_temp = self.analyzer.get_readings(
            device, self.analyzer.PARAM_RETURN_TEMP, start_time, end_time
        )
        compressor = self.analyzer.get_readings(
            device, self.analyzer.PARAM_COMPRESSOR_FREQ, start_time, end_time
        )
        degree_mins = self.analyzer.get_readings(
            device, self.analyzer.PARAM_DM_CURRENT, start_time, end_time
        )

        # Create dashboard
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

        # Title
        fig.suptitle(f'Nibe Heat Pump Dashboard - Last {hours_back} Hours',
                    fontsize=16, fontweight='bold')

        # 1. Temperatures
        ax1 = fig.add_subplot(gs[0, :])
        if outdoor:
            times, values = zip(*outdoor)
            ax1.plot(times, values, label='Outdoor', linewidth=2)
        if supply:
            times, values = zip(*supply)
            ax1.plot(times, values, label='Supply', linewidth=2)
        if return_temp:
            times, values = zip(*return_temp)
            ax1.plot(times, values, label='Return', linewidth=2)

        ax1.set_ylabel('Temperature (°C)')
        ax1.set_title('System Temperatures')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        # 2. Compressor
        ax2 = fig.add_subplot(gs[1, 0])
        if compressor:
            times, values = zip(*compressor)
            ax2.plot(times, values, linewidth=2, color='purple')
            ax2.fill_between(times, values, alpha=0.3, color='purple')

        ax2.set_ylabel('Frequency (Hz)')
        ax2.set_title('Compressor Operation')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        # 3. Degree Minutes
        ax3 = fig.add_subplot(gs[1, 1])
        if degree_mins:
            times, values = zip(*degree_mins)
            ax3.plot(times, values, linewidth=2, color='teal')
            ax3.axhline(y=-200, color='green', linestyle='--', label='Target')
            ax3.axhspan(-300, -100, alpha=0.1, color='green')

        ax3.set_ylabel('Degree Minutes')
        ax3.set_title('Heating Balance')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

        # 4. Current Metrics
        ax4 = fig.add_subplot(gs[2, :])
        ax4.axis('off')

        cop_str = f"{metrics.estimated_cop:.2f}" if metrics.estimated_cop is not None else "N/A"

        metrics_text = f"""
        CURRENT SYSTEM STATUS

        Temperatures:
        • Outdoor:  {metrics.avg_outdoor_temp:>6.1f}°C
        • Indoor:   {metrics.avg_indoor_temp:>6.1f}°C
        • Supply:   {metrics.avg_supply_temp:>6.1f}°C
        • Return:   {metrics.avg_return_temp:>6.1f}°C
        • Δ (Supply-Return): {metrics.avg_supply_temp - metrics.avg_return_temp:.1f}°C

        Settings:
        • Heating Curve: {metrics.heating_curve}
        • Curve Offset:  {metrics.curve_offset}

        Performance:
        • Degree Minutes: {metrics.degree_minutes:.0f} (target: -200)
        • Estimated COP:  {cop_str}
        • Compressor:     {metrics.avg_compressor_freq:.0f} Hz
        """

        ax4.text(0.1, 0.5, metrics_text, fontsize=11, verticalalignment='center',
                fontfamily='monospace', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()

        logger.info(f"Dashboard saved to {output_file}")
        return output_file


def main():
    """Generate all visualizations"""
    logger.info("="*80)
    logger.info("GENERATING HEAT PUMP VISUALIZATIONS")
    logger.info("="*80 + "\n")

    visualizer = HeatPumpVisualizer()

    try:
        # Temperature plot
        logger.info("Creating temperature plot...")
        visualizer.plot_temperatures(hours_back=24)

        # Efficiency plot
        logger.info("Creating efficiency plot...")
        visualizer.plot_efficiency(hours_back=24)

        # COP plot (7 days)
        logger.info("Creating COP trend plot...")
        visualizer.plot_cop_estimate(hours_back=168)

        # Dashboard
        logger.info("Creating dashboard...")
        visualizer.create_dashboard(hours_back=24)

        logger.info("\n" + "="*80)
        logger.info("✅ All visualizations created successfully!")
        logger.info("="*80)
        logger.info("\nGenerated files:")
        logger.info("  data/temperature_plot.png")
        logger.info("  data/efficiency_plot.png")
        logger.info("  data/cop_plot.png")
        logger.info("  data/dashboard.png")

    except Exception as e:
        logger.error(f"Error generating visualizations: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
