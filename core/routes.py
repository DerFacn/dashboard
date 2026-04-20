import os
import json
import uuid
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from flask import Blueprint, request, render_template, session, redirect, url_for, jsonify, send_file, Response
from werkzeug.utils import secure_filename

requests.packages.urllib3.disable_warnings()

main_bp = Blueprint('main', __name__)

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

# ФІКС: Робимо абсолютний шлях до кореня проекту, піднімаючись на рівень вище папки core
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
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

@main_bp.route('/')
def index():
    links = load_data()
    groups = sorted(list(set(link.get('group', 'Other') for link in links if link.get('group'))))
    return render_template('index.html', links=links, groups=groups, is_admin=session.get('admin', False))

@main_bp.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == ADMIN_PASSWORD:
        session['admin'] = True
    return redirect(url_for('main.index'))

@main_bp.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('main.index'))

@main_bp.route('/api/icon')
def get_icon():
    link_id = request.args.get('id')
    links = load_data()
    link = next((l for l in links if l['id'] == link_id), None)
    
    if not link:
        return Response(FALLBACK_ICON, mimetype='image/svg+xml')

    # First, check if there is a custom icon and if it is enabled
    custom_icon = link.get('custom_icon')
    if custom_icon:
        custom_path = os.path.join(ICONS_DIR, custom_icon)
        if os.path.exists(custom_path):
            return send_file(custom_path)

    # If there is no custom icon, scrape from the URL
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

@main_bp.route('/api/action', methods=['POST'])
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

        # Handle custom icon upload
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
    return redirect(url_for('main.index'))