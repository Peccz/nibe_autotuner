# Nibe Autotuner - GUI Guide

## 🚀 Quick Start

### Launch the GUI

```bash
./run_gui.sh
```

The web interface will automatically open in your browser at: **http://localhost:8501**

## 📊 Features

### Dashboard Tab
- **Real-time Metrics**: COP, Degree Minutes, Delta T, Compressor Frequency
- **Visual Indicators**: ✅ Good, ⚠️ Warning, ❌ Alert
- **Temperature Overview**: Outdoor, Indoor, Supply, Return
- **System Settings**: Current heating curve and offset

### Recommendations Tab
- **AI-driven Suggestions**: Optimization opportunities ranked by confidence
- **Detailed Explanations**: Why changes are recommended
- **Expected Impact**: What improvements to expect
- **Easy Tracking**: Mark recommendations as applied

### Visualizations Tab
- **Dashboard**: Complete system overview
- **Temperature Trends**: Historical temperature data
- **Efficiency Metrics**: Compressor operation and degree minutes
- **COP Analysis**: 7-day efficiency trends

### Historical Data Tab
- **Parameter Query**: View any parameter's history
- **Statistics**: Average, min, max, standard deviation
- **Interactive Charts**: Zoom and explore data
- **Raw Data Export**: Download as needed

### Documentation Tab
- **System Overview**: Understanding key metrics
- **Scientific Foundation**: Research-backed approach
- **Command Reference**: Quick access to common commands
- **Resources**: Links to documentation and GitHub

## 🎨 User Interface

### Sidebar Controls
- **Analysis Period**: Choose 6h, 12h, 24h, 48h, 72h, or 7 days
- **Database Stats**: View data collection status
- **Quick Actions**:
  - 🔄 Refresh Data
  - 📈 Generate Plots

### Status Indicators

**COP (Coefficient of Performance)**
- ✅ >= 3.0: Excellent efficiency
- ⚠️ 2.5-3.0: Good efficiency
- ❌ < 2.5: Low efficiency (may be due to outdoor temperature)

**Degree Minutes**
- ✅ -300 to -100: Optimal comfort zone
- ⚠️ -400 to -300 or -100 to 0: Monitor
- ❌ < -400 or > 0: Action required

**Delta T (Supply-Return Differential)**
- ✅ 5-8°C: Optimal heat extraction
- ⚠️ 3-5°C or 8-10°C: Suboptimal
- ❌ < 3°C or > 10°C: Inefficient operation

## 💡 Tips

### First Time Setup
1. Install and start data logger: `./install_service.sh`
2. Wait 24-48 hours for initial data collection
3. Launch GUI: `./run_gui.sh`
4. Generate visualizations from sidebar

### Regular Use
- Check dashboard daily for system status
- Review recommendations weekly
- Apply suggested changes gradually
- Monitor results for 2-3 days after changes

### Data Analysis
- Use longer analysis periods (7 days) for trend analysis
- Compare before/after data when making changes
- Export historical data for detailed review
- Generate fresh plots after significant changes

## 🔧 Troubleshooting

### "No data in database"
- Run data logger: `sudo systemctl start nibe-autotuner`
- Check logs: `journalctl -u nibe-autotuner -f`
- Verify authentication: `python src/auth.py`

### "Error loading metrics"
- Ensure database exists: `ls -lh data/nibe_autotuner.db`
- Check data collection: Use Historical Data tab
- Restart GUI: Press Ctrl+C and run `./run_gui.sh` again

### Visualizations not showing
- Click "Generate Plots" in sidebar
- Wait for generation to complete
- Check `data/` folder for PNG files
- Refresh browser if needed

### Performance issues
- Reduce analysis period (use 24h instead of 7 days)
- Clear browser cache
- Restart Streamlit server

## 🌐 Remote Access

To access the GUI from other devices on your network:

1. Edit `run_gui.sh` and change:
   ```bash
   --server.address localhost
   ```
   to:
   ```bash
   --server.address 0.0.0.0
   ```

2. Access from other devices using your computer's IP:
   ```
   http://YOUR_IP:8501
   ```

   Find your IP with: `ip addr show` (Linux) or `ipconfig` (Windows)

## 📱 Mobile Access

The GUI is responsive and works on:
- Smartphones
- Tablets
- Laptops
- Desktop browsers

Simply navigate to the URL in your mobile browser.

## 🔐 Security Note

The GUI runs locally and does not require authentication by default. If exposing to network:

1. Use firewall rules to restrict access
2. Consider setting up authentication (Streamlit supports this)
3. Use VPN for remote access
4. Keep your system updated

## 🎯 Advanced Features

### Custom Analysis
Use Historical Data tab to:
- Query specific parameters
- Export data to CSV
- Create custom visualizations
- Compare different time periods

### Integration with API
The GUI uses the same analyzer backend as the REST API. You can:
- Run both GUI and API simultaneously
- Use API for mobile app development
- Access data programmatically
- Build custom integrations

## 📚 Resources

- **GitHub**: https://github.com/Peccz/nibe_autotuner
- **Documentation**: See [README.md](README.md)
- **Scientific Baseline**: See [docs/SCIENTIFIC_BASELINE.md](docs/SCIENTIFIC_BASELINE.md)
- **API Documentation**: Run `python src/api_server.py` and visit http://localhost:8000/docs

## 🆘 Support

If you encounter issues:

1. Check logs: `journalctl -u nibe-autotuner -f`
2. Verify data collection is working
3. Try restarting the GUI
4. Check GitHub issues for similar problems
5. Create a new issue with error details

## 🔄 Updates

To update to the latest version:

```bash
cd nibe_autotuner
git pull
pip install -r requirements.txt
./run_gui.sh
```

---

**Enjoy your optimized heat pump! 🔥**
