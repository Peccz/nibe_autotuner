with open('base.html', 'r') as f:
    lines = f.readlines()

insert_idx = -1
for i, line in enumerate(lines):
    if "href=\"/settings\"" in line: # Find settings link
        # Go back to find <li class="nav-item"> start or just insert before
        insert_idx = i - 1 # Assuming standard bootstrap list structure
        break

if insert_idx != -1:
    new_link = """
                <li class="nav-item">
                    <a class="nav-link" href="/learning">
                        <i class="bi bi-cpu"></i> Inlärning
                    </a>
                </li>
"""
    lines.insert(insert_idx, new_link)

with open('base_updated.html', 'w') as f:
    f.writelines(lines)
