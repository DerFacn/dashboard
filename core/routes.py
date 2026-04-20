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
PAGE_TITLE = os.environ.get('PAGE_TITLE', 'My Dashboard')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'links.json')
ICONS_DIR = os.path.join(DATA_DIR, 'icons')
STATIC_DIR = os.path.join(BASE_DIR, 'core', 'static')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
BGS_DIR = os.path.join(DATA_DIR, 'backgrounds')

FALLBACK_ICON = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#cdd6f4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>'''
FAVICON_SVG_CONTENT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#89b4fa"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/></svg>'''

def init_env():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ICONS_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(BGS_DIR, exist_ok=True)
    
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump([], f)
            
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {
            "active_profile": "Dark",
            "profiles": {
                "Dark": {"bg": "#1e1e2e", "card": "#313244", "text": "#cdd6f4", "accent": "#89b4fa", "bg_mode": "solid", "gradient": "", "bg_image": ""},
                "Light": {"bg": "#eff1f5", "card": "#e6e9ef", "text": "#4c4f69", "accent": "#1e66f5", "bg_mode": "solid", "gradient": "", "bg_image": ""}
            }
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(default_settings, f)
            
    favicon_path = os.path.join(STATIC_DIR, 'favicon.svg')
    if not os.path.exists(favicon_path):
        with open(favicon_path, 'w', encoding='utf-8') as f:
            f.write(FAVICON_SVG_CONTENT)

def load_data():
    init_env()
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
        return sorted(data, key=lambda x: x.get('order', 0))

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_settings():
    init_env()
    with open(SETTINGS_FILE, 'r') as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

@main_bp.route('/')
def index():
    links = load_data()
    # Показуємо приховані групи адміну, але не показуємо їх юзерам, якщо всі лінки в них приховані
    is_admin = session.get('admin', False)
    visible_links = links if is_admin else [l for l in links if not l.get('is_hidden')]
    groups = sorted(list(set(link.get('group', 'Інше') for link in visible_links if link.get('group'))))
    
    settings = load_settings()
    active_profile_name = settings.get('active_profile', 'Dark')
    theme = settings['profiles'].get(active_profile_name, settings['profiles']['Dark'])
    
    return render_template('index.html', 
                           links=links, 
                           groups=groups, 
                           is_admin=is_admin,
                           page_title=PAGE_TITLE,
                           theme=theme,
                           profiles=settings['profiles'],
                           active_profile_name=active_profile_name)

@main_bp.route('/login', methods=['POST'])
def login():
    if request.form.get('password') == ADMIN_PASSWORD:
        session['admin'] = True
    return redirect(url_for('main.index'))

@main_bp.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('main.index'))

# Новий роут для швидкої перевірки статусу (працює у фоні)
@main_bp.route('/api/status')
def check_status():
    url = request.args.get('url')
    if not url:
        return jsonify({"status": "down"})
    try:
        # Тайм-аут 3 секунди, ігноруємо сертифікати
        res = requests.get(url, timeout=3, verify=False, allow_redirects=True)
        # Якщо 404 або помилка сервера (5xx) - лежить. Якщо 2xx, 3xx або навіть 401/403 (є авторизація) - живий.
        if res.status_code < 500 and res.status_code != 404:
            return jsonify({"status": "up"})
        else:
            return jsonify({"status": "down"})
    except Exception:
        return jsonify({"status": "down"})

@main_bp.route('/api/icon')
def get_icon():
    link_id = request.args.get('id')
    links = load_data()
    link = next((l for l in links if l['id'] == link_id), None)
    
    if not link:
        return Response(FALLBACK_ICON, mimetype='image/svg+xml')

    custom_icon = link.get('custom_icon')
    if custom_icon:
        custom_path = os.path.join(ICONS_DIR, custom_icon)
        if os.path.exists(custom_path):
            return send_file(custom_path)

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

@main_bp.route('/api/bg')
def get_bg():
    img = request.args.get('img')
    if not img:
        return Response("Not found", 404)
    path = os.path.join(BGS_DIR, secure_filename(img))
    if os.path.exists(path):
        return send_file(path)
    return Response("Not found", 404)

@main_bp.route('/api/theme', methods=['POST'])
def api_theme():
    if not session.get('admin'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
    
    action = request.form.get('action')
    settings = load_settings()

    if action == 'save_profile':
        profile_name = request.form.get('profile_name')
        bg_mode = request.form.get('bg_mode')
        
        bg_image = settings['profiles'].get(profile_name, {}).get('bg_image', '')
        if bg_mode == 'image':
            bg_file = request.files.get('bg_file')
            if bg_file and bg_file.filename:
                ext = os.path.splitext(secure_filename(bg_file.filename))[1]
                bg_filename = f"bg_{uuid.uuid4().hex}{ext}"
                bg_file.save(os.path.join(BGS_DIR, bg_filename))
                bg_image = bg_filename

        new_profile = {
            "bg": request.form.get('bg_color'),
            "card": request.form.get('card_color'),
            "text": request.form.get('text_color'),
            "accent": request.form.get('accent_color'),
            "bg_mode": bg_mode,
            "gradient": request.form.get('gradient_css'),
            "bg_image": bg_image
        }
        
        settings['profiles'][profile_name] = new_profile
        settings['active_profile'] = profile_name

    elif action == 'switch_profile':
        profile_name = request.form.get('profile_name')
        if profile_name in settings['profiles']:
            settings['active_profile'] = profile_name

    elif action == 'delete_profile':
        profile_name = request.form.get('profile_name')
        if profile_name in settings['profiles'] and profile_name not in ['Dark', 'Light']:
            del settings['profiles'][profile_name]
            if settings['active_profile'] == profile_name:
                settings['active_profile'] = 'Dark'

    save_settings(settings)
    return redirect(url_for('main.index'))

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
        group = request.form.get('group') or 'Інше'
        description = request.form.get('description', '')
        use_custom = request.form.get('use_custom_icon') == 'on'
        is_hidden = request.form.get('is_hidden') == 'on' # Отримуємо статус прихованості
        
        existing_link = next((l for l in links if l['id'] == link_id), None)
        custom_icon_filename = None

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
            'custom_icon': custom_icon_filename,
            'is_hidden': is_hidden
        }
        
        if existing_link:
            existing_link.update(link_data)
        else:
            link_data['order'] = len(links)
            links.append(link_data)
            
    elif action == 'delete':
        link_id = request.form.get('id')
        links = [l for l in links if l['id'] != link_id]
        
    elif action == 'reorder':
        # Логіка для Drag and Drop (обробляється через AJAX)
        ordered_ids_json = request.form.get('ordered_ids')
        if ordered_ids_json:
            try:
                ordered_ids = json.loads(ordered_ids_json)
                id_to_order = {link_id: idx for idx, link_id in enumerate(ordered_ids)}
                for l in links:
                    l['order'] = id_to_order.get(l['id'], l.get('order', 999))
                links.sort(key=lambda x: x.get('order', 0))
            except json.JSONDecodeError:
                pass
        save_data(links)
        return jsonify({"status": "ok"})

    save_data(links)
    return redirect(url_for('main.index'))