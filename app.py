import os
import json
import uuid
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from flask import Flask, request, render_template_string, session, redirect, url_for, jsonify, send_file, Response
from werkzeug.utils import secure_filename

requests.packages.urllib3.disable_warnings()

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

DATA_DIR = 'data'
DATA_FILE = os.path.join(DATA_DIR, 'links.json')
ICONS_DIR = os.path.join(DATA_DIR, 'icons')

FALLBACK_ICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cdd6f4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>'''

def init_env():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ICONS_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)

def load_data():
    init_env()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        return sorted(data, key=lambda x: x.get('order', 0))

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/')
def index():
    links = load_data()
    groups = sorted(list(set(link.get('group', 'Інше') for link in links if link.get('group'))))
    return render_template_string(HTML_TEMPLATE, links=links, groups=groups, is_admin=session.get('admin', False))

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == ADMIN_PASSWORD:
        session['admin'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/api/icon')
def get_icon():
    link_id = request.args.get('id')
    links = load_data()
    link = next((l for l in links if l['id'] == link_id), None)
    
    if not link:
        return Response(FALLBACK_ICON, mimetype='image/svg+xml')

    # Спочатку перевіряємо, чи є кастомна іконка і чи вона увімкнена
    custom_icon = link.get('custom_icon')
    if custom_icon:
        custom_path = os.path.join(ICONS_DIR, custom_icon)
        if os.path.exists(custom_path):
            return send_file(custom_path)

    # Якщо кастомної немає, скрапимо з URL
    url = link.get('url')
    if not url:
        return Response(FALLBACK_ICON, mimetype='image/svg+xml')

    domain = urlparse(url).netloc
    icon_path = os.path.join(ICONS_DIR, f"{domain}.ico")
    
    if os.path.exists(icon_path):
        return send_file(icon_path)

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        soup = BeautifulSoup(res.text, 'html.parser')
        icon_link = soup.find('link', rel=lambda x: x and 'icon' in x.lower())
        
        icon_url = urljoin(url, icon_link.get('href')) if icon_link and icon_link.get('href') else urljoin(url, '/favicon.ico')
        icon_res = requests.get(icon_url, headers=headers, timeout=5, verify=False)
        
        if icon_res.status_code == 200:
            with open(icon_path, 'wb') as f:
                f.write(icon_res.content)
            return send_file(icon_path)
    except Exception:
        pass

    return Response(FALLBACK_ICON, mimetype='image/svg+xml')

@app.route('/api/action', methods=['POST'])
def api_action():
    if not session.get('admin'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    action = request.form.get('action')
    links = load_data()

    if action == 'save':
        link_id = request.form.get('id') or str(uuid.uuid4())
        title = request.form.get('title')
        url = request.form.get('url')
        group = request.form.get('group') or 'Other'
        description = request.form.get('description', '')
        use_custom = request.form.get('use_custom_icon') == 'on'
        
        existing_link = next((l for l in links if l['id'] == link_id), None)
        custom_icon_filename = None

        # Обробка завантаження кастомної іконки
        if use_custom:
            icon_file = request.files.get('icon_file')
            if icon_file and icon_file.filename:
                ext = os.path.splitext(secure_filename(icon_file.filename))[1]
                custom_icon_filename = f"custom_{link_id}{ext}"
                icon_file.save(os.path.join(ICONS_DIR, custom_icon_filename))
            elif existing_link:
                custom_icon_filename = existing_link.get('custom_icon')

        link_data = {
            'id': link_id,
            'title': title,
            'url': url,
            'group': group,
            'description': description,
            'custom_icon': custom_icon_filename
        }
        
        if existing_link:
            existing_link.update(link_data)
        else:
            link_data['order'] = len(links)
            links.append(link_data)
            
    elif action == 'delete':
        link_id = request.form.get('id')
        links = [l for l in links if l['id'] != link_id]
        
    elif action in ['move_up', 'move_down']:
        link_id = request.form.get('id')
        idx = next((i for i, l in enumerate(links) if l['id'] == link_id), None)
        if idx is not None:
            swap_idx = idx - 1 if action == 'move_up' else idx + 1
            if 0 <= swap_idx < len(links):
                links[idx], links[swap_idx] = links[swap_idx], links[idx]
                for i, l in enumerate(links):
                    l['order'] = i

    save_data(links)
    return redirect(url_for('index'))

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Dashboard</title>
    <style>
        :root { --bg: #1e1e2e; --card: #313244; --text: #cdd6f4; --accent: #89b4fa; --danger: #f38ba8; }
        body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; margin: 0; padding: 2rem; display: flex; flex-direction: column; align-items: center; }
        .container { width: 100%; max-width: 900px; display: flex; flex-direction: column; align-items: center; }
        h1 { margin-bottom: 2rem; font-weight: 500; letter-spacing: 1px; color: var(--text); }
        .groups { display: flex; gap: 0.5rem; margin-bottom: 2rem; flex-wrap: wrap; justify-content: center; }
        .group-btn { background: var(--card); border: 1px solid transparent; color: var(--text); padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer; transition: 0.2s; font-size: 0.9rem; }
        .group-btn.active, .group-btn:hover { border-color: var(--accent); color: var(--accent); }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 1rem; width: 100%; }
        .card { background: var(--card); padding: 1.2rem; border-radius: 12px; text-decoration: none; color: var(--text); display: flex; align-items: center; gap: 1rem; transition: transform 0.2s, box-shadow 0.2s; position: relative; border: 1px solid rgba(255,255,255,0.05); }
        .card:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(0,0,0,0.2); border-color: var(--accent); }
        .card img { width: 36px; height: 36px; border-radius: 8px; background: #fff; padding: 2px; object-fit: contain; }
        .card h3 { margin: 0; font-size: 1rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .card-group { font-size: 0.75rem; color: #a6adc8; margin-top: 4px; display: block; }
        .admin-btn-float { position: fixed; bottom: 2rem; right: 2rem; background: var(--card); border: 1px solid rgba(255,255,255,0.1); padding: 1rem; border-radius: 50%; cursor: pointer; color: var(--text); display: flex; align-items: center; justify-content: center; transition: 0.2s; box-shadow: 0 4px 10px rgba(0,0,0,0.3); z-index: 10; text-decoration: none; }
        .admin-btn-float:hover { background: var(--accent); color: var(--bg); }
        .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); align-items: center; justify-content: center; z-index: 100; }
        .modal.active { display: flex; }
        .modal-content { background: var(--bg); padding: 2rem; border-radius: 16px; width: 320px; display: flex; flex-direction: column; gap: 1rem; border: 1px solid var(--card); box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
        .modal-content h2 { margin: 0 0 1rem 0; font-size: 1.2rem; }
        input[type="text"], input[type="url"], input[type="password"] { padding: 0.8rem; border-radius: 8px; border: 1px solid var(--card); background: #11111b; color: var(--text); width: 100%; box-sizing: border-box; }
        input:focus { outline: none; border-color: var(--accent); }
        .btn { background: var(--accent); color: var(--bg); border: none; padding: 0.8rem; border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; transition: 0.2s; }
        .btn:hover { opacity: 0.9; }
        .close-btn { background: transparent; color: var(--text); border: 1px solid var(--card); margin-top: 0.5rem; }
        .card-actions { position: absolute; top: -10px; right: -10px; display: none; gap: 4px; z-index: 5; }
        .card:hover .card-actions { display: flex; }
        .action-btn { background: var(--accent); border: none; color: var(--bg); width: 24px; height: 24px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.2); }
        .action-btn.delete { background: var(--danger); }
        .checkbox-group { display: flex; align-items: center; gap: 0.5rem; font-size: 0.9rem; margin-top: 0.5rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>My resources</h1>
        
        <div class="groups">
            <button class="group-btn active" onclick="filterGroup('all', this)">All</button>
            {% for group in groups %}
            <button class="group-btn" onclick="filterGroup('{{ group }}', this)">{{ group }}</button>
            {% endfor %}
        </div>

        <div class="grid" id="linksGrid">
            {% for link in links %}
            <a href="{{ link.url }}" class="card" data-group="{{ link.group }}" target="_blank" title="{{ link.description if link.description else link.title }}">
                <img src="/api/icon?id={{ link.id }}" alt="icon">
                <div>
                    <h3>{{ link.title }}</h3>
                    <span class="card-group">{{ link.group }}</span>
                </div>
                {% if is_admin %}
                <div class="card-actions" onclick="event.preventDefault();">
                    <button class="action-btn" onclick="postAction('move_up', '{{ link.id }}')" title="Left">←</button>
                    <button class="action-btn" onclick="postAction('move_down', '{{ link.id }}')" title="Right">→</button>
                    <button class="action-btn" 
                            data-id="{{ link.id }}" data-title="{{ link.title }}" data-url="{{ link.url }}" 
                            data-group="{{ link.group }}" data-desc="{{ link.description|default('') }}" 
                            data-custom-icon="{{ link.custom_icon|default('') }}"
                            onclick="openEditModal(this)" title="Edit">✎</button>
                    <button class="action-btn delete" onclick="if(confirm('Delete?')) postAction('delete', '{{ link.id }}')" title="Delete">✕</button>
                </div>
                {% endif %}
            </a>
            {% endfor %}
        </div>
    </div>

    {% if is_admin %}
        <div style="position: fixed; bottom: 2rem; right: 6rem; z-index: 10;">
            <a href="/logout" class="admin-btn-float" style="position: relative; right: 0; bottom: 0;">🚪</a>
        </div>
        <div class="admin-btn-float" onclick="openAddModal()">➕</div>
    {% else %}
        <div class="admin-btn-float" onclick="document.getElementById('loginModal').classList.add('active')">🔒</div>
    {% endif %}

    <div class="modal" id="loginModal">
        <div class="modal-content">
            <h2>Admin panel</h2>
            <form action="/login" method="POST">
                <input type="password" name="password" placeholder="Password" required autofocus>
                <button type="submit" class="btn" style="margin-top: 1rem;">Login</button>
                <button type="button" class="btn close-btn" onclick="document.getElementById('loginModal').classList.remove('active')">Cancel</button>
            </form>
        </div>
    </div>

    <div class="modal" id="editModal">
        <div class="modal-content">
            <h2 id="modalTitle">Add resource</h2>
            <form action="/api/action" method="POST" id="editForm" enctype="multipart/form-data">
                <input type="hidden" name="action" value="save">
                <input type="hidden" name="id" id="formId">
                <input type="text" name="title" id="formTitle" placeholder="Name (e.g.: Proxmox)" required>
                <input type="url" name="url" id="formUrl" placeholder="URL (e.g.: https://example.com)" required>
                <input type="text" name="group" id="formGroup" placeholder="Group (e.g.: Monitorings)" required>
                <input type="text" name="description" id="formDescription" placeholder="Description (optional)">
                
                <div class="checkbox-group">
                    <input type="checkbox" name="use_custom_icon" id="formUseCustomIcon">
                    <label for="formUseCustomIcon">Use custom icon</label>
                </div>
                <input type="file" name="icon_file" id="formIconFile" accept="image/*" style="display: none; padding: 0; background: transparent; border: none;">

                <button type="submit" class="btn" style="margin-top: 1rem;">Save</button>
                <button type="button" class="btn close-btn" onclick="document.getElementById('editModal').classList.remove('active')">Cancel</button>
            </form>
        </div>
    </div>

    <script>
        function filterGroup(group, btnElement) {
            document.querySelectorAll('.group-btn').forEach(btn => btn.classList.remove('active'));
            btnElement.classList.add('active');
            document.querySelectorAll('.card').forEach(card => {
                card.style.display = (group === 'all' || card.dataset.group === group) ? 'flex' : 'none';
            });
        }

        function postAction(action, id) {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/api/action';
            ['action', 'id'].forEach(name => {
                const input = document.createElement('input');
                input.name = name; input.value = name === 'action' ? action : id;
                form.appendChild(input);
            });
            document.body.appendChild(form);
            form.submit();
        }

        // Логіка показу кнопки завантаження файлу
        document.getElementById('formUseCustomIcon').addEventListener('change', function() {
            document.getElementById('formIconFile').style.display = this.checked ? 'block' : 'none';
        });

        function openAddModal() {
            document.getElementById('modalTitle').innerText = 'Add resource';
            document.getElementById('formId').value = '';
            document.getElementById('formTitle').value = '';
            document.getElementById('formUrl').value = '';
            document.getElementById('formGroup').value = '';
            document.getElementById('formDescription').value = '';
            document.getElementById('formUseCustomIcon').checked = false;
            document.getElementById('formIconFile').style.display = 'none';
            document.getElementById('editModal').classList.add('active');
        }

        function openEditModal(btnElement) {
            const data = btnElement.dataset;
            document.getElementById('modalTitle').innerText = 'Edit resource';
            document.getElementById('formId').value = data.id;
            document.getElementById('formTitle').value = data.title;
            document.getElementById('formUrl').value = data.url;
            document.getElementById('formGroup').value = data.group;
            document.getElementById('formDescription').value = data.desc;
            
            const hasCustom = data.customIcon && data.customIcon !== 'None' && data.customIcon !== '';
            document.getElementById('formUseCustomIcon').checked = hasCustom;
            document.getElementById('formIconFile').style.display = hasCustom ? 'block' : 'none';
            
            document.getElementById('editModal').classList.add('active');
        }
    </script>
</body>
</html>
"""