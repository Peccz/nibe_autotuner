with open('temp_mobile_app_broken.py', 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "except Exception as e:" in line:
        # Check next line
        if i + 1 < len(lines):
            next_line = lines[i+1].strip()
            if next_line.startswith("@app.route"):
                # Missing return statement!
                lines.insert(i+1, "        return jsonify({'success': False, 'error': str(e)}), 500\n")

with open('temp_mobile_app_fixed.py', 'w') as f:
    f.writelines(lines)
