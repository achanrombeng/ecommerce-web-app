from datetime import datetime
import traceback
from venv import logger
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import GenderEnum, Image, ImageUsers, Order, OrderStatusEnum, PaymentMethodEnum, Product, ProductOrder, RoleEnum, User, db, Cart
import os
import base64
import hashlib
import uuid
import midtransclient
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('OAUTH_CLIENT_ID'),
    client_secret=os.environ.get('OAUTH_CLIENT_SECRET'),
    server_metadata_url=os.environ.get('OAUTH_SERVER_METADATA_URL'),
    client_kwargs={'scope': 'openid email profile'}
)

# konfigurasi Midtrans
snap = midtransclient.Snap(
    is_production=False,  # Set ke False untuk Sandbox atau development
    server_key=os.environ.get('SNAP_SERVER_KEY'),
    client_key=os.environ.get('SNAP_CLIENT_KEY')
)

# Tambahkan baris ini agar Jinja2 mengenali filter b64encode
@app.template_filter('b64encode')
def b64encode_filter(data):
    if data:
        return base64.b64encode(data).decode('utf-8')
    return ""

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).filter_by(id=user_id).first()


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        phone_number = request.form.get('phone_number')
        address = request.form.get('address')
        gender = request.form.get('gender')


        # Validasi
        if password != confirm_password:
            flash('Password dan konfirmasi password tidak cocok!', 'error')
            return render_template('register.html')

        if db.session.query(User).filter_by(email=email).first():
            flash('Email sudah digunakan!', 'error')
            return render_template('register.html')

        # Buat user baru
        new_user = User(
            first_name=first_name, 
            last_name=last_name,
            email=email,
            phone_number=phone_number,
            address=address,
            gender=gender,
            role='USER'  
        )
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()

        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
        

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        if not email or not password:
            flash('Email dan password harus diisi!', 'error')
            return render_template('login.html')

        user = db.session.query(User).filter_by(email=email).first()

        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            flash(f'Login berhasil! Selamat datang {user.first_name}', 'success')
            
            if user.is_admin():
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Login gagal. Periksa email dan password!', 'error')

        
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    # Mengarahkan user ke Google
    redirect_uri = url_for('google_auth', _external=True)
    print(f"Redirect URI yang dikirim ke Google: {redirect_uri}")
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_auth():
    try:
        token = google.authorize_access_token()
        # Cara paling aman mengambil data user
        respon = google.get('https://openidconnect.googleapis.com/v1/userinfo')
        user_info = respon.json()
        
        print(f"DEBUG USER_INFO: {user_info}") # LIHAT DI TERMINAL 

        email = user_info.get('email')
        if not email:
            flash("Gagal mendapatkan email dari Google.", "error")
            return redirect(url_for('login'))

        user = db.session.query(User).filter_by(email=email).first()

        if not user:
            # Mapping data dengan default value untuk menghindari NOT NULL error
            user = User(
                email=email,
                first_name=user_info.get('given_name', 'User'),
                last_name=user_info.get('family_name', ''),
                password_hash=str(uuid.uuid4()), 
                is_active=True,
                role=RoleEnum.USER, 
                gender=GenderEnum.OTHER,
                # Tambahkan field kosong jika di DB diatur NOT NULL
                phone_number='-', 
                address='-'
            )
            db.session.add(user)
            db.session.commit()

        login_user(user)
        flash(f'Login berhasil! Selamat datang {user.first_name}', 'success')
        
        if user.role == RoleEnum.ADMIN:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))

    except Exception as e:
        db.session.rollback()
        # Print detail error ke terminal agar tahu penyebab pastinya
        import traceback
        traceback.print_exc() 
        print(f"Error Detail: {str(e)}")
        flash("Gagal login dengan Google.", "error")
        return redirect(url_for('login'))

    except Exception as e:
        db.session.rollback()
        print(f"Error saat Google Auth: {str(e)}")
        flash("Gagal login dengan Google.", "error")
        return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    user.profile_image_url = None
    if user.image_profile:
        img = user.image_profile[0]
        if img.file_data:
            base64_data = base64.b64encode(img.file_data).decode('utf-8')
            user.profile_image_url = f"data:{img.file_type};base64,{base64_data}"
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Query order counts per status (lebih efisien)
        from sqlalchemy import func
        
        order_stats = db.session.query(
            Order.status,
            func.count(Order.id).label('count')
        ).filter_by(user_id=current_user.id).group_by(Order.status).all()
        
        # Convert to dictionary
        status_counts = {status.value: count for status, count in order_stats}
        
        pending = status_counts.get('PENDING', 0)
        approve = status_counts.get('APPROVE', 0)
        cancel = status_counts.get('CANCEL', 0)
        
        # Query all orders (jika masih diperlukan untuk ditampilkan)
        orders = db.session.query(Order).filter_by(user_id=current_user.id).all()
        
        # Query products with images
        products = db.session.query(Product).options(joinedload(Product.images)).all()
        
        # Process each product to handle memoryview/image data
        processed_products = []
        for product in products:
            product_data = {
                'id': product.id,
                'product_name': product.product_name,
                'product_price': product.product_price,
                'product_stock': product.product_stock,
                'product_category': product.product_category,
                'product_image': None
            }

            # Ambil gambar pertama jika ada
            if product.images and len(product.images) > 0:
                first_image = product.images[0]
                if first_image.file_data:
                    try:
                        # Cek format data URI
                        if isinstance(first_image.file_data, str) and first_image.file_data.startswith('data:'):
                            product_data['product_image'] = first_image.file_data
                        else:
                            # Convert memoryview/bytes to base64
                            image_bytes = bytes(first_image.file_data)
                            mime_type = detect_mime_type(image_bytes)
                            base64_image = base64.b64encode(image_bytes).decode('utf-8')
                            product_data['product_image'] = f'data:{mime_type};base64,{base64_image}'
                    except Exception as e:
                        print(f"Error processing image for product {product.id}: {e}")
            
            processed_products.append(product_data)
            
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        import traceback
        traceback.print_exc()
        processed_products = []
        orders = []
        pending = approve = cancel = 0

    return render_template('dashboard.html', 
                         user=user, 
                         products=processed_products, 
                         orders=orders, 
                         pending=pending, 
                         approve=approve, 
                         cancel=cancel)
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    users = db.session.query(User).all()
    total_admins = len([user for user in users if user.is_admin()])
    total_users = len(users) - total_admins
    total_products = db.session.query(Product).count()
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin_dashboard.html', users=users, total_admins=total_admins, total_users=total_users, total_products=total_products, orders=orders)

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
def admin_products():
    users = db.session.query(User).all()
    total_products = db.session.query(Product).count()
    total_admins = len([user for user in users if user.is_admin()])
    total_users = len(users) - total_admins
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    if not current_user.is_admin():
        flash('Akses ditolak!', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            # Ambil filter dari request.form
            name_filter = request.form.get('name', '').strip()
            category_filter = request.form.get('category', '').strip()
            max_price_filter = request.form.get('maxPrice', '').strip()
            status_filter = request.form.get('status', '').strip()

            # Query dengan joinedload 'images' sesuai model Product Anda
            query = db.session.query(Product).options(joinedload(Product.images))

            if name_filter:
                query = query.filter(func.lower(Product.product_name).like(f'%{name_filter.lower()}%'))
            if category_filter:
                query = query.filter(Product.product_category == category_filter)
            if max_price_filter:
                try:
                    query = query.filter(Product.product_price <= float(max_price_filter))
                except ValueError: pass
            
            if status_filter:
                if status_filter.lower() == 'aktif':
                    query = query.filter(Product.product_status == True)
                elif status_filter.lower() == 'nonaktif':
                    query = query.filter(Product.product_status == False)

            products = query.order_by(Product.id.desc()).all()
            
            data = []
            for p in products:
                # --- LOGIKA GAMBAR ---
                img_base64 = None
                if p.images and len(p.images) > 0:
                    first_img = p.images[0]
                    if first_img.file_data:
                        try:
                            b64 = base64.b64encode(first_img.file_data).decode('utf-8')
                            img_base64 = f"data:{first_img.file_type};base64,{b64}"
                        except: img_base64 = None

                # Pastikan harga dikonversi ke float sebelum diformat
                try:
                    raw_price = float(p.product_price) if p.product_price else 0
                    price_formatted = f"{raw_price:,.0f}"
                except (ValueError, TypeError):
                    price_formatted = "0"

                # --- LOGIKA STATUS ---
                display_status = 'Available' if p.product_status else 'Unavailable'
                if (p.product_stock or 0) <= 0:
                    display_status = 'Out Of Stock'

                data.append({
                    'product_id': p.id,
                    'product_name': p.product_name,
                    'product_category': p.product_category or 'Tanpa Kategori',
                    'product_price': price_formatted,
                    'product_stock': p.product_stock or 0,
                    'product_status': display_status,
                    'product_image': img_base64
                })

            return jsonify({'data': data})

        except Exception as e:
            print(f"DEBUG ERROR: {str(e)}")
            return jsonify({'data': [], 'error': str(e)}), 500

    # GET Request: Ambil statistik untuk tampilan awal
    stats = {
        'total': db.session.query(Product).count(),
        'active': db.session.query(Product).filter(Product.product_status == True).count(),
        'low': db.session.query(Product).filter(Product.product_stock < 10, Product.product_stock > 0).count(),
        'out': db.session.query(Product).filter(Product.product_stock <= 0).count()
    }
    
    return render_template('admin_produk.html', **stats, can_update=True, can_delete=True, user=users, total_products=total_products, orders=orders, total_admins=total_admins, total_users=total_users)
@app.route('/admin/products/delete/<int:product_id>', methods=['DELETE'])
@login_required
def admin_delete_product(product_id):
    try:
        print(f"\n{'='*60}")
        print(f"DELETE REQUEST for product_id: {product_id}")
        print(f"{'='*60}")
        
        product = db.session.query(Product).filter_by(id=product_id).first()
        
        if not product:
            print(f"⚠️  Product with ID {product_id} not found")
            return jsonify({
                'success': False, 
                'message': 'Produk tidak ditemukan!'
            }), 404
        
        product_name = product.product_name
        print(f"Found product: {product_name}")
        
        # Hapus file gambar jika ada
        if product.product_image:
            try:
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], product.product_image)
                if os.path.exists(image_path):
                    os.remove(image_path)
                    print(f"✓ Image deleted: {image_path}")
            except Exception as e:
                print(f"⚠️  Error deleting image: {e}")
        
        db.session.delete(product)
        db.session.commit()
        
        print(f"✓ Product '{product_name}' deleted successfully")
        print(f"{'='*60}\n")

        return jsonify({
            'success': True, 
            'message': f'Produk "{product_name}" berhasil dihapus!'
        })
    
    except Exception as e:
        db.session.rollback()
        
        print(f"\n{'!'*60}")
        print(f"ERROR deleting product {product_id}:")
        print(f"{'!'*60}")
        import traceback
        print(traceback.format_exc())
        print(f"{'!'*60}\n")
        
        return jsonify({
            'success': False, 
            'message': f'Terjadi kesalahan: {str(e)}'
        }), 500
    
    finally:
        db.session.close()

@app.route('/admin/add-product', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    users = db.session.query(User).all()
    total_admins = len([user for user in users if user.is_admin()])
    total_users = len(users) - total_admins
    total_products = db.session.query(Product).count()
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    if request.method == 'POST':
        try:
            # Ambil data dari form
            product_name = request.form.get('product_name')
            product_description = request.form.get('product_description')
            product_category = request.form.get('product_category')
            product_price = request.form.get('product_price')
            product_stock = request.form.get('product_stock')
            product_status = request.form.get('product_status', '1')

            # Validasi data wajib
            if not product_name or not product_price or not product_category:
                flash('Nama produk, harga, dan kategori harus diisi!', 'error')
                return render_template('admin_add_produk.html')
            
            # Konversi tipe data
            try:
                product_price = int(product_price)
                product_stock = int(product_stock) if product_stock else 0
            except ValueError:
                flash('Harga dan stok harus berupa angka!', 'error')
                return render_template('admin_add_produk.html')

            # Handle product_status
            product_status_bool = product_status == '1'

            # Buat product baru
            new_product = Product(
                product_name=product_name,
                product_description=product_description,
                product_category=product_category,
                product_price=product_price,
                product_stock=product_stock,
                product_status=product_status_bool,
                created_at=datetime.now()
            )

            
            
            # Handle upload gambar
            image_uploaded = False
            if 'product_image' in request.files:
                image_file = request.files['product_image']
                if image_file and image_file.filename != '':
                    # Validasi tipe file
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in image_file.filename and \
                       image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        
                        # Baca file sebagai binary
                        image_data = image_file.read()
                        
                        # Validasi ukuran file (max 5MB)
                        if len(image_data) > 5 * 1024 * 1024:
                            flash('Ukuran gambar terlalu besar. Maksimal 5MB.', 'error')
                            db.session.rollback()
                            return render_template('admin_add_produk.html')
                        
                        from werkzeug.utils import secure_filename
                        import base64
                        
                        filename = secure_filename(image_file.filename)
                        file_size = len(image_data)
                        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpeg'
                        
                        mime_types = {
                            'png': 'image/png',
                            'jpg': 'image/jpeg',
                            'jpeg': 'image/jpeg',
                            'gif': 'image/gif',
                            'webp': 'image/webp'
                        }
                        
                        file_type = mime_types.get(file_extension, 'image/jpeg')

                        
                        
                        # Untuk tabel Image (simpan sebagai base64 string)
                        
                        
                        new_image = Image(
                            product_id=new_product.id,
                            file_data=image_data,
                            file_name=filename,
                            file_size=file_size,
                            file_type=file_type
                        )

                        new_product.images.append(new_image)
                        image_uploaded = True
                    else:
                        flash('Format file tidak didukung. Gunakan PNG, JPG, JPEG, GIF, atau WebP.', 'error')
                        db.session.rollback()
                        return render_template('admin_add_produk.html')
            db.session.add(new_product)
            db.session.commit()
            flash('Produk berhasil ditambahkan!', 'success')
            return redirect(url_for('admin_products'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error adding product: {e}")
            import traceback
            traceback.print_exc()
            flash('Error menambahkan produk: ' + str(e), 'error')
    
    return render_template('admin_add_produk.html', users=users, total_admins=total_admins, total_users=total_users, total_products=total_products, orders=orders) 

@app.route('/admin/edit-product')
@login_required
def admin_edit_product():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    
    # Ambil produk yang akan diedit
    product = db.session.query(Product).filter_by(id=request.args.get('product_id')).first()
    
    # Konversi status boolean ke string untuk template
    product_status_value = '1' if product.product_status else '0'
    
    return render_template('admin_edit_produk.html', 
                         product=product, 
                         product_status_value=product_status_value)

@app.route('/admin/update-product/<int:product_id>', methods=['POST'])
@login_required
def admin_update_product(product_id):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Akses ditolak!'}), 403
    
    product = db.session.query(Product).filter_by(id=product_id).first()
    
    try:
        # 1. Ambil data dari form
        product.product_name = request.form.get('product_name')
        product.product_description = request.form.get('product_description')
        product.product_category = request.form.get('product_category')
        product_price = request.form.get('product_price')
        product_stock = request.form.get('product_stock')
        # Ambil status (1 untuk Aktif, 0 untuk Nonaktif)
        product_status = request.form.get('product_status')
        
        # 2. Validasi sederhana
        if not product.product_name or not product_price:
            return jsonify({'success': False, 'message': 'Nama dan harga wajib diisi!'}), 400

        # 3. Konversi tipe data
        product.product_price = int(product_price)
        product.product_stock = int(product_stock) if product_stock else 0
        product.product_status = (product_status == '1')
        
        # 4. Handle Gambar (jika ada upload baru)
        if 'product_image' in request.files:
            image_file = request.files['product_image']
            if image_file and image_file.filename != '':
                # Hapus gambar lama jika ada
                if product.images:
                    for img in product.images:
                        db.session.delete(img)
                
                image_data = image_file.read()
                new_image = Image(
                    product_id=product.id,
                    file_data=image_data,
                    file_name=image_file.filename,
                    file_size=len(image_data),
                    file_type=image_file.content_type
                )
                db.session.add(new_image)

        product.updated_at = datetime.now()
        db.session.commit()
        
        # WAJIB: Mengembalikan JSON, bukan redirect/render_template
        return jsonify({'success': True, 'message': 'Produk berhasil diperbarui!'})

    except Exception as e:
        db.session.rollback()
        # Jika error, kirim pesan error dalam bentuk JSON
        return jsonify({'success': False, 'message': f'Terjadi kesalahan server: {str(e)}'}), 500

@app.route('/admin/orders', methods=['GET', 'POST'])
@login_required
def admin_orders():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))

    # Ambil data Admin yang sedang login untuk Sidebar (base-admin.html)
    admin_obj = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    admin_profile_url = None
    if admin_obj and admin_obj.image_profile:
        img = admin_obj.image_profile[0]
        if img.file_data:
            base64_admin = base64.b64encode(img.file_data).decode('utf-8')
            admin_profile_url = f"data:{img.file_type};base64,{base64_admin}"
    current_user.profile_image_url = admin_profile_url

    # Handle POST request untuk DataTables AJAX
    if request.method == 'POST':
        customer_filter = request.form.get('customer', '').strip()
        date_filter = request.form.get('date', '').strip()
        max_amount = request.form.get('maxAmount', '').strip()
        status_filter = request.form.get('status', '').strip()
        
        # Query orders dengan joins dan eager load profil image user
        query = db.session.query(Order).options(
            joinedload(Order.product_orders).joinedload(ProductOrder.product),
            joinedload(Order.user).joinedload(User.image_profile)
        )
        
        # Filter logic
        if customer_filter:
            query = query.join(Order.user).filter(
                db.or_(
                    User.first_name.ilike(f'%{customer_filter}%'),
                    User.last_name.ilike(f'%{customer_filter}%'),
                    User.email.ilike(f'%{customer_filter}%')
                )
            )
        
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
                query = query.filter(db.func.date(Order.created_at) == filter_date)
            except ValueError:
                pass
        
        if max_amount:
            try:
                query = query.filter(Order.amount <= float(max_amount))
            except ValueError:
                pass
        
        if status_filter:
            if status_filter.lower() == 'pending':
                query = query.filter(Order.status == OrderStatusEnum.PENDING)
            elif status_filter.lower() == 'approve':
                query = query.filter(Order.status == OrderStatusEnum.APPROVE)
            elif status_filter.lower() == 'cancel':
                query = query.filter(Order.status == OrderStatusEnum.CANCEL)
        
        orders = query.order_by(Order.created_at.desc()).all()
        
        data = []
        for order in orders:
            # Hitung total items
            total_items = sum((po.quantity or 0) for po in order.product_orders)
            amount_formatted = "{:,.0f}".format(order.amount or 0)
            
            # LOGIKA IMAGE PROFILE PELANGGAN
            u = order.user
            customer_avatar = None
            if u.image_profile:
                img_u = u.image_profile[0]
                if img_u.file_data:
                    try:
                        b64_u = base64.b64encode(img_u.file_data).decode('utf-8')
                        customer_avatar = f"data:{img_u.file_type};base64,{b64_u}"
                    except:
                        customer_avatar = None
            
            # Jika tidak ada foto, gunakan UI-Avatars
            if not customer_avatar:
                customer_avatar = f"https://ui-avatars.com/api/?name={u.first_name}+{u.last_name}&background=0077b5&color=fff"
            
            customer_name = f"{u.first_name} {u.last_name}"
            
            data.append({
                'id': order.id,
                'user_id': order.user_id,
                'total_items': total_items,
                'customer_name': customer_name,
                'customer_email': u.email,
                'customer_avatar': customer_avatar,
                'created_at': order.created_at.isoformat(),
                'date': order.created_at.strftime("%d %B %Y"),
                'time': order.created_at.strftime("%H:%M"),
                'amount': amount_formatted,
                'payment_method': order.payment_method.value if order.payment_method else '-',
                'status': order.status.value if hasattr(order.status, 'value') else str(order.status)
            })
        
        return jsonify({'data': data})
    
    # Handle GET request (Render Awal)
    user = db.session.query(User).all()
    total_admins = len([u for u in user if u.is_admin()])
    total_users = len(user) - total_admins
    total_products = db.session.query(Product).count()
    orders_all = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).all()
    
    pending = sum(1 for o in orders_all if o.status == OrderStatusEnum.PENDING)
    approved = sum(1 for o in orders_all if o.status == OrderStatusEnum.APPROVE)
    cancel = sum(1 for o in orders_all if o.status == OrderStatusEnum.CANCEL)
    
    return render_template('admin_order.html', 
                           orders=orders_all, 
                           pending=pending, 
                           approved=approved, 
                           cancel=cancel,
                           can_update=True,
                           total_admins=total_admins,
                           total_users=total_users,
                           total_products=total_products)

@app.route('/admin/orders-detail/<int:order_id>/<int:user_id>')
@login_required
def admin_order_detail(order_id, user_id):
    # Cek admin terlebih dahulu
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        user = db.session.query(User).filter_by(id=user_id).first()
        if not user:
            flash('User tidak ditemukan!', 'error')
            return redirect(url_for('admin_orders'))
        
        order = db.session.query(Order).options(
            joinedload(Order.product_orders).joinedload(ProductOrder.product).joinedload(Product.images)
        ).filter_by(id=order_id, user_id=user.id).first()
        
        if not order:
            flash('Order tidak ditemukan untuk user ini!', 'error')
            return redirect(url_for('admin_orders'))
        
        # Format harga untuk setiap product_order
        for product_order in order.product_orders:
            # Format harga produk
            product_price = float(product_order.product.product_price) if product_order.product.product_price else 0
            product_order.formatted_price = "{:,.0f}".format(product_price)
            
            # Format subtotal (harga x quantity)
            quantity = int(product_order.quantity) if product_order.quantity else 0
            subtotal = product_price * quantity
            product_order.formatted_subtotal = "{:,.0f}".format(subtotal)
            
            # --- LOGIKA GAMBAR ---
            img_base64 = None
            if product_order.product.images and len(product_order.product.images) > 0:
                first_img = product_order.product.images[0]
                if first_img.file_data:
                    try:
                        b64 = base64.b64encode(first_img.file_data).decode('utf-8')
                        img_base64 = f"data:{first_img.file_type};base64,{b64}"
                    except:
                        img_base64 = None
            
            # Simpan gambar ke product_order untuk diakses di template
            product_order.product_image = img_base64 if img_base64 else 'https://via.placeholder.com/48'
        
        # Format total order
        order_amount = float(order.amount) if order.amount else 0
        order.formatted_total = "{:,.0f}".format(order_amount)
        
        # Data untuk sidebar/statistik
        users = db.session.query(User).all()
        total_admins = sum(1 for u in users if u.is_admin())
        total_users = len(users) - total_admins
        total_products = db.session.query(Product).count()
        
        # Data orders untuk keperluan lain jika diperlukan
        orders = db.session.query(Order).options(
            joinedload(Order.product_orders).joinedload(ProductOrder.product),
            joinedload(Order.user)
        ).order_by(Order.created_at.desc()).all()
        
        return render_template(
            'admin_order_detail.html',
            users=users,
            total_admins=total_admins,
            total_users=total_users,
            total_products=total_products,
            orders=orders,
            order=order,
            user=user
        )
        
    except Exception as e:
        print("Error detail:", str(e))
        import traceback
        traceback.print_exc()
        flash('Terjadi kesalahan saat mengambil data order: ' + str(e), 'error')
        return redirect(url_for('admin_orders'))

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))

    # 1. Ambil data Admin yang sedang login (untuk sidebar base-admin.html)
    # Kita ambil objek admin secara terpisah agar profile_image_url bisa ditempelkan
    admin_obj = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    
    admin_profile_url = None
    if admin_obj and admin_obj.image_profile:
        img = admin_obj.image_profile[0]
        if img.file_data:
            base64_admin = base64.b64encode(img.file_data).decode('utf-8')
            admin_profile_url = f"data:{img.file_type};base64,{base64_admin}"
    
    # Simpan ke current_user agar bisa diakses oleh sidebar di template manapun
    current_user.profile_image_url = admin_profile_url

    # 2. LOGIKA POST (Request dari DataTables AJAX)
    if request.method == 'POST':
        name_filter = request.form.get('name', '').strip()
        email_filter = request.form.get('email', '').strip()
        role_filter = request.form.get('role', '').strip()
        gender_filter = request.form.get('gender', '').strip()
        
        # Query User dengan eager load gambar
        query = db.session.query(User).options(joinedload(User.image_profile))
        
        if name_filter:
            query = query.filter(User.first_name.ilike(f'%{name_filter}%'))
        if email_filter:
            query = query.filter(User.email.ilike(f'%{email_filter}%'))
        if role_filter:
            query = query.filter(User.role == role_filter.upper())
        if gender_filter:
            query = query.filter(User.gender == gender_filter.upper())
        
        filtered_users = query.all()
        
        data_list = []
        for u in filtered_users:
            # Konversi gambar tiap user di tabel
            u_pic = None
            if u.image_profile:
                img_u = u.image_profile[0]
                if img_u.file_data:
                    try:
                        b64_u = base64.b64encode(img_u.file_data).decode('utf-8')
                        u_pic = f"data:{img_u.file_type};base64,{b64_u}"
                    except:
                        u_pic = None

            data_list.append({
                'id': u.id,
                'first_name': u.first_name,
                'last_name': u.last_name or '',
                'email': u.email,
                'role': u.role.value if hasattr(u.role, 'value') else str(u.role),
                'gender': u.gender.value if hasattr(u.gender, 'value') else str(u.gender),
                'birth_date': u.birth_date.strftime("%d %B %Y") if u.birth_date else '-',
                'profile_picture': u_pic
            })
        
        return jsonify({'data': data_list})
    
    # 3. LOGIKA GET (Render Halaman Pertama Kali)
    users_all = db.session.query(User).all()
    total_admins = len([u for u in users_all if u.role == 'ADMIN' or (hasattr(u.role, 'value') and u.role.value == 'ADMIN')])
    total_users = len(users_all) - total_admins
    total_products = db.session.query(Product).count()
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    
    return render_template('admin_user.html', 
                         users=users_all, 
                         total_admins=total_admins, 
                         total_users=total_users,
                         total_products=total_products,
                         orders=orders,
                         can_update=True)

@app.route('/admin/add-user', methods=['GET', 'POST'])
@login_required
def admin_add_user():
    users = db.session.query(User).all()
    total_admins = len([user for user in users if user.is_admin()])
    total_users = len(users) - total_admins
    total_products = db.session.query(Product).count()
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    if request.method == 'POST':
        try:
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            role = request.form.get('role', 'USER')
            phone_number = request.form.get('phone_number')
            address = request.form.get('address')
            gender_value = request.form.get('gender')
            birth_date_str = request.form.get('birth_date')

            # Validasi password
            if password != confirm_password:
                return jsonify({
                    'success': False,
                    'message': 'Password dan konfirmasi password tidak cocok!'
                }), 400
            
            # Cek email sudah digunakan
            if db.session.query(User).filter_by(email=email).first():
                return jsonify({
                    'success': False,
                    'message': 'Email sudah digunakan!'
                }), 400
            
            # Buat user baru
            new_user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password_hash=generate_password_hash(password),
                phone_number=phone_number,
                address=address,
                role=RoleEnum(role) if role else RoleEnum.USER
            )
            
            # Set gender jika ada
            if gender_value:
                new_user.gender = GenderEnum(gender_value)
            
            # Set birth date jika ada
            if birth_date_str:
                new_user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
            
            db.session.add(new_user)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'User berhasil ditambahkan!'
            }), 201
            
        except Exception as e:
            db.session.rollback()
            print(f'Error menambahkan user: {e}')
            import traceback
            traceback.print_exc()
            
            return jsonify({
                'success': False,
                'message': f'Terjadi kesalahan: {str(e)}'
            }), 500
    
    # GET request - tampilkan form
    return render_template('admin_add_user.html', users=users, total_admins=total_admins, total_users=total_users, total_products=total_products, orders=orders)

@app.route('/admin/edit-user')
@login_required
def admin_edit_user():
    user = db.session.query(User).filter_by(id=request.args.get('user_id')).first()
    users = db.session.query(User).all()
    total_admins = len([user for user in users if user.is_admin()])
    total_users = len(users) - total_admins
    total_products = db.session.query(Product).count()
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    return render_template('admin_edit_user.html', user=user, users=users, total_admins=total_admins, total_users=total_users, total_products=total_products, orders=orders)


@app.route('/admin/update-user/<int:user_id>', methods=['POST'])
@login_required
def admin_update_user(user_id):
    if not current_user.is_admin():
        return jsonify({'success': False, 'message': 'Akses ditolak!'}), 403
        
    try:
        user = db.session.query(User).filter_by(id=user_id).first()
        
        # 1. Update Data Teks
        user.first_name = request.form.get('first_name')
        user.last_name = request.form.get('last_name')
        user.role = request.form.get('role')
        user.phone_number = request.form.get('phone_number')
        user.address = request.form.get('address')
        user.gender = request.form.get('gender')

        # 2. Update Tanggal Lahir
        birth_date_str = request.form.get('birth_date')
        if birth_date_str:
            user.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()

        # 3. Handle Foto Profil (Jika ada upload)
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '':
                # Baca file dan ubah ke Base64 (atau simpan ke folder sesuai struktur )
                image_data = file.read()
                # Jika  menyimpan sebagai string base64 di database:
                base64_image = base64.b64encode(image_data).decode('utf-8')
                user.profile_picture = f"data:{file.content_type};base64,{base64_image}"

        db.session.commit()
        return jsonify({'success': True, 'message': 'Profil user berhasil diperbarui'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'}), 500
@app.route('/admin/report')
@login_required
def admin_report():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin_report.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout!', 'info')
    return redirect(url_for('login'))

@app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    if not current_user.is_admin():
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = db.session.query(User).filter_by(id=user_id).get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'aktif' if user.is_active else 'non-aktif'
    return jsonify({
        'message': f'User {user.first_name} berhasil di{status}kan', 
        'is_active': user.is_active
    })

# Create tables and default admin
with app.app_context():
    db.create_all()
    
    # Create default admin user if not exists
    if not db.session.query(User).filter_by(email='admin@example.com').first():
        try:
            admin = User(
                first_name='Admin',
                last_name='System',
                email='admin@example.com', 
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully")
        except Exception as e:
            print(f"Error creating admin user: {e}")
            db.session.rollback()
        finally:
            db.session.close()
import base64

@app.route('/produk-user')
@login_required
def produk_user():
    user = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    user.profile_image_url = None
    if user.image_profile:
        img = user.image_profile[0]
        if img.file_data:
            base64_data = base64.b64encode(img.file_data).decode('utf-8')
            user.profile_image_url = f"data:{img.file_type};base64,{base64_data}"
    try:
        products = db.session.query(Product).options(joinedload(Product.images)).all()
        
        # Process each product to handle memoryview/image data
        processed_products = []
        for product in products:
            product_data = {
                'id': product.id,
                'product_name': product.product_name,
                'product_price': product.product_price,
                'product_stock': product.product_stock,
                'product_category': product.product_category,
                'product_image': None  # Default None
            }

            # Ambil gambar pertama jika ada
            if product.images and len(product.images) > 0:
                first_image = product.images[0]
                if first_image.file_data:
                    # Convert memoryview to bytes if necessary
                    image_bytes = bytes(first_image.file_data)
                    
                    # Detect MIME type
                    mime_type = detect_mime_type(image_bytes)
                    
                    # Encode to base64 for embedding in HTML
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    product_data['product_image'] = f'data:{mime_type};base64,{base64_image}'
            
            processed_products.append(product_data)
        
        return render_template('produk-user.html', products=processed_products, user=user)
        
    except Exception as e:
        print(f"Error loading products: {e}")
        import traceback
        traceback.print_exc()
        return render_template('produk-user.html', products=[])


# Helper function untuk deteksi MIME type
def detect_mime_type(image_bytes):
    """Deteksi MIME type dari file signature"""
    # Check file signatures (magic numbers)
    if image_bytes.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    elif image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    elif image_bytes.startswith(b'GIF87a') or image_bytes.startswith(b'GIF89a'):
        return 'image/gif'
    elif image_bytes.startswith(b'RIFF') and image_bytes[8:12] == b'WEBP':
        return 'image/webp'
    elif image_bytes.startswith(b'BM'):
        return 'image/bmp'
    else:
        # Default fallback
        return 'image/jpeg'
    
@app.route('/form-order-user', methods=['GET'])
@login_required
def form_order_user():
    user = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    user_data = current_user
    cart_ids = session.get('checkout_cart_ids', [])
    cart_items = []
    user.profile_image_url = None
    if user.image_profile:
        img = user.image_profile[0]
        if img.file_data:
            base64_data = base64.b64encode(img.file_data).decode('utf-8')
            user.profile_image_url = f"data:{img.file_type};base64,{base64_data}"
    if cart_ids:
        cart_items = db.session.query(Cart).filter(Cart.id.in_(cart_ids), Cart.user_id == current_user.id).all()
        for item in cart_items:
            item.product.product_price = float(item.product.product_price or 0)
            
    product_id = request.args.get('product_id')
    product_now = None
    if product_id and not cart_items:
        product_now = db.session.query(Product).get(product_id)
        if product_now:
            product_now.product_price = float(product_now.product_price or 0)

    return render_template('form_order_user.html', user_data=user_data, cart_items=cart_items, product_now=product_now, user=user)


@app.route('/api/order/process', methods=['POST'])
@login_required
def process_order():
    try:
        data = request.get_json()
        payment_method = data.get('payment')
        
        # 1. Ambil data dari session atau productId
        cart_ids = session.get('checkout_cart_ids', [])
        items_to_order = []
        total_amount = 0
        midtrans_items = [] # Untuk rincian di struk Midtrans

        if cart_ids:
            # SKENARIO A: DARI KERANJANG
            cart_items = db.session.query(Cart).filter(Cart.id.in_(cart_ids)).all()
            if not cart_items:
                return jsonify({'success': False, 'message': 'Keranjang kosong'}), 400
                
            for item in cart_items:
                price = int(float(item.product.product_price or 0))
                qty = int(item.quantity)
                subtotal = price * qty
                total_amount += subtotal
                
                items_to_order.append((item.product, qty, item))
                # Format untuk Midtrans
                midtrans_items.append({
                    "id": str(item.product.id),
                    "price": price,
                    "quantity": qty,
                    "name": item.product.product_name[:50] # Maks 50 karakter
                })
        else:
            # SKENARIO B: BELI LANGSUNG
            product = db.session.query(Product).get(data.get('productId'))
            if not product:
                return jsonify({'success': False, 'message': 'Produk tidak ditemukan'}), 404
            
            price = int(float(product.product_price or 0))
            qty = int(data.get('quantity', 1))
            total_amount = price * qty
            
            items_to_order.append((product, qty, None))
            midtrans_items.append({
                "id": str(product.id),
                "price": price,
                "quantity": qty,
                "name": product.product_name[:50]
            })

        # 2. Buat Order Baru di Database
        new_order = Order(
            user_id=current_user.id,
            amount=total_amount,
            payment_method=payment_method,
            status="PENDING", # Default status
            created_at=datetime.now()
        )
        
        db.session.add(new_order)
        db.session.flush() # Ambil ID order tanpa commit dulu

        # 3. Logika Midtrans (Hanya jika TRANSFER_BANK)
        snap_token = None
        if payment_method == 'TRANSFER_BANK':
            midtrans_order_id = f"ORDER-{new_order.id}-{int(datetime.now().timestamp())}"
            
            # Gabungkan nama depan dan belakang jika tersedia
            full_name_db = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or "Customer"

            param = {
                "transaction_details": {
                    "order_id": midtrans_order_id,
                    "gross_amount": int(total_amount)
                },
                "item_details": midtrans_items,
                "customer_details": {
                    "first_name": data.get('fullName') or full_name_db,
                    "email": data.get('email') or current_user.email,
                    "phone": data.get('phone') or current_user.phone_number or ""
                },
                "usage_limit": 1
            }

            transaction = snap.create_transaction(param)
            snap_token = transaction['token']
            new_order.midtrans_order_id = midtrans_order_id 

        # 4. Simpan Detail Produk & Kurangi Stok
        for prod, qty, cart_obj in items_to_order:
            if prod.product_stock < qty:
                db.session.rollback()
                return jsonify({'success': False, 'message': f'Stok {prod.product_name} tidak cukup'}), 400
                
            product_order = ProductOrder(
                product_id=prod.id, 
                order_id=new_order.id, 
                quantity=qty
            )
            db.session.add(product_order)
            
            # Kurangi stok (Sistem "Booking")
            prod.product_stock -= qty
            
            if cart_obj:
                db.session.delete(cart_obj)

        # 5. Finalisasi
        db.session.commit()
        session.pop('checkout_cart_ids', None) # Bersihkan session checkout

        return jsonify({
            'success': True, 
            'message': 'Pesanan berhasil dibuat!' if payment_method == 'COD' else 'Silahkan selesaikan pembayaran.',
            'snap_token': snap_token
        }), 201

    except Exception as e:
        db.session.rollback()
        print(f"CRITICAL ERROR: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal Server Error'}), 500
    

# webhook update payment status dari midtrans
# @app.route('/api/payment/callback', methods=['POST'])
# def midtrans_webhook():
#     data = request.get_json()
#     print("WEBHOOK DATA RECEIVED:", data)
    
#     # 1. Identifikasi Transaksi
#     mid_order_id = data.get('order_id')
#     status_code = data.get('status_code')
#     gross_amount = data.get('gross_amount')
#     signature_key = data.get('signature_key')
#     transaction_status = data.get('transaction_status')
    
#     # 2. Verifikasi Signature (Keamanan)
#     server_key = os.environ.get('SNAP_SERVER_KEY') 
#     payload = f"{mid_order_id}{status_code}{gross_amount}{server_key}"
#     calc_signature = hashlib.sha512(payload.encode()).hexdigest()

#     if calc_signature != signature_key:
#         return jsonify({"success": False, "message": "Invalid Signature"}), 401

#     # 3. Cari Order di Database
#     # Kita filter berdasarkan midtrans_order_id yang kamu simpan saat checkout
#     order = db.session.query(Order).filter(Order.id == mid_order_id).first()
    
#     if not order:
#         return jsonify({"success": False, "message": "Order tidak ditemukan"}), 404

#     # 4. Trigger Perubahan Status
#     try:
#         if transaction_status in ['capture', 'settlement']:
#             # Pembayaran Berhasil
#             order.status = OrderStatusEnum.APPROVE
            
#         elif transaction_status in ['expire', 'cancel', 'deny']:
#             # Pembayaran Gagal/Expired
#             order.status = OrderStatusEnum.CANCEL
            
#             # Balikkan Stok: Cari item yang dipesan melalui ProductOrder
#             # Karena model Order menggunakan secondary='product_order_db'
#             items = db.session.query(ProductOrder).filter_by(order_id=order.id).all()
#             for item in items:
#                 prod = db.session.query(Product).get(item.product_id)
#                 if prod:
#                     prod.product_stock += item.quantity

#         db.session.commit()
#         return "OK", 200

#     except Exception as e:
#         db.session.rollback()
#         print(f"WEBHOOK ERROR: {str(e)}")
#         return jsonify({"success": False, "error": "Internal Server Error"}), 500

@app.route('/order-user')
@login_required
def order_user():
    user = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    user.profile_image_url = None
    if user.image_profile:
        img = user.image_profile[0]
        if img.file_data:
            base64_data = base64.b64encode(img.file_data).decode('utf-8')
            user.profile_image_url = f"data:{img.file_type};base64,{base64_data}"
    # Ambil data order dengan relasi produk dan gambarnya
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product).joinedload(Product.images)
    ).filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    
    # Fungsi bantu untuk konversi gambar ke Base64
    def get_image_data(product):
        if product.images and len(product.images) > 0:
            img = product.images[0]
            if img.file_data:
                try:
                    if isinstance(img.file_data, str) and img.file_data.startswith('data:'):
                        return img.file_data
                    image_bytes = bytes(img.file_data)
                    mime_type = detect_mime_type(image_bytes)
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    return f'data:{mime_type};base64,{base64_image}'
                except Exception as e:
                    print(f"Error: {e}")
        return None

    # Tambahkan atribut image_url ke setiap produk di dalam order secara dinamis
    for order in orders:
        for po in order.product_orders:
            po.product.image_url = get_image_data(po.product)
        
    return render_template('order-user.html', orders=orders, user=user)

@app.route('/order/detail/<int:order_id>')
@login_required
def order_detail(order_id):
    user = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    # Ambil data order, pastikan order tersebut milik user yang sedang login
    order = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product).joinedload(Product.images)
    ).filter_by(id=order_id).first()
    
    def get_image_data(product):
        if product.images and len(product.images) > 0:
            img = product.images[0]
            if img.file_data:
                try:
                    if isinstance(img.file_data, str) and img.file_data.startswith('data:'):
                        return img.file_data
                    image_bytes = bytes(img.file_data)
                    mime_type = detect_mime_type(image_bytes)
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    return f'data:{mime_type};base64,{base64_image}'
                except Exception as e:
                    print(f"Error: {e}")
        return None

    # Tambahkan atribut image_url ke setiap produk di dalam order secara dinamis
    for po in order.product_orders:
        po.product.image_url = get_image_data(po.product)

    if order.user_id != current_user.id:
        flash("Anda tidak memiliki akses ke pesanan ini.", "danger")
        return redirect(url_for('orders'))
        
    return render_template('detail-order-user.html', order=order, user=user)



@app.route('/cart')
@login_required
def cart_user():
    user = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    user.profile_image_url = None
    if user.image_profile:
        img = user.image_profile[0]
        if img.file_data:
            base64_data = base64.b64encode(img.file_data).decode('utf-8')
            user.profile_image_url = f"data:{img.file_type};base64,{base64_data}"
    # Ambil items dengan relasi produk dan gambarnya
    cart_items = db.session.query(Cart).options(
        joinedload(Cart.product).joinedload(Product.images)
    ).filter_by(user_id=current_user.id).all()
    
    
    # Fungsi konversi yang sama dengan halaman order
    def get_image_data(product):
        if product.images and len(product.images) > 0:
            img = product.images[0]
            if img.file_data:
                try:
                    if isinstance(img.file_data, str) and img.file_data.startswith('data:'):
                        return img.file_data
                    image_bytes = bytes(img.file_data)
                    mime_type = detect_mime_type(image_bytes)
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    return f'data:{mime_type};base64,{base64_image}'
                except Exception as e:
                    print(f"Error: {e}")
        return None

    # Mengisi atribut image_url secara dinamis
    for item in cart_items:
        item.product.image_url = get_image_data(item.product)

    subtotal = sum(float(item.product.product_price or 0) * int(item.quantity or 0) for item in cart_items)
    
    return render_template('cart-user.html', cart_items=cart_items, subtotal=subtotal, total=subtotal, user=user)

@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    try:
        # gunakan first() untuk mendapatkan satu produk
        product = db.session.query(Product).filter_by(id=product_id).first()
        
        if not product:
            return jsonify({'success': False, 'message': 'Produk tidak ditemukan'}), 404
        
        # Cek stok (Aktifkan kembali agar valid)
        if product.product_stock <= 0:
            return jsonify({'success': False, 'message': 'Stok produk habis!'}), 400

        # Cek apakah produk sudah ada di keranjang user
        # Pastikan tipe data konsisten (Integer)
        item = db.session.query(Cart).filter_by(
            user_id=int(current_user.id), 
            product_id=int(product_id)
        ).first()
        
        if item:
            # Jika stok mencukupi, tambah quantity
            if item.quantity < product.product_stock:
                item.quantity += 1
            else:
                return jsonify({'success': False, 'message': 'Jumlah melebihi stok tersedia'}), 400
        else:
            new_item = Cart(user_id=current_user.id, product_id=product_id, quantity=1)
            db.session.add(new_item)
        
        db.session.commit()
        return jsonify({'success': True, 'message': f'{product.product_name} ditambahkan ke keranjang'})

    except Exception as e:
        db.session.rollback()
        print(f"Error Cart: {str(e)}") # Log untuk debugging
        return jsonify({'success': False, 'message': 'Gagal menambahkan produk'}), 500
    
@app.route('/api/cart/checkout', methods=['POST'])
@login_required
def cart_checkout_api():
    try:
        data = request.get_json()
        cart_ids = data.get('cart_ids', [])

        if not cart_ids:
            return jsonify({'success': False, 'message': 'Pilih produk dahulu'}), 400

        # Simpan ke session agar bisa dibaca di halaman form-order
        session['checkout_cart_ids'] = cart_ids
        
        return jsonify({
            'success': True,
            'message': 'Lanjut ke pengisian form...',
            'redirect_url': url_for('form_order_user') # Redirect ke halaman form
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
@app.route('/cart/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_cart_item(item_id):
    item = db.session.query(Cart).filter_by(id=item_id).first()
    if not item:
        return jsonify({'success': False, 'message': 'Item tidak ditemukan'}), 404
    if item.user_id == current_user.id:
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Produk dihapus'})
    return jsonify({'success': False, 'message': 'Unauthorized'}), 403

@app.route('/cart/update/<int:product_id>', methods=['POST'])
@login_required
def update_cart_qty(product_id):
    try:
        data = request.get_json()
        action = data.get('action')
        
        # Cari item keranjang milik user yang sedang login
        cart_item = db.session.query(Cart).filter_by(id=product_id, user_id=current_user.id).first()
        
        if not cart_item:
            return jsonify({'success': False, 'message': 'Item tidak ditemukan'}), 404
        
        if action == 'plus':
            cart_item.quantity += 1
        elif action == 'minus':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
            else:
                return jsonify({'success': False, 'message': 'Jumlah minimal adalah 1'}), 400
        else:
            return jsonify({'success': False, 'message': 'Aksi tidak valid'}), 400

        db.session.commit()
        
        # Hitung subtotal baru untuk item ini
        new_subtotal = float(cart_item.product.product_price) * cart_item.quantity
        
        return jsonify({
            'success': True,
            'new_qty': cart_item.quantity,
            'new_subtotal': new_subtotal,
            'message': 'Berhasil memperbarui jumlah'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/profile-user', methods=['GET'])
def profile_user():
    # Ambil satu user berdasarkan ID (bukan list)
    users = db.session.query(User).options(joinedload(User.image_profile)).filter_by(id=current_user.id).first()
    
    # Fungsi untuk mengolah data biner dari tabel ImageUsers
    def get_profile_image_url(user):
        if user.image_profile and len(user.image_profile) > 0:
            # Mengambil item pertama karena relasi image_profile adalah list
            img = user.image_profile[0]
            if img.file_data:
                try:
                    # Konversi LargeBinary ke base64 string
                    base64_data = base64.b64encode(img.file_data).decode('utf-8')
                    # Gunakan file_type dari database (misal: image/jpeg)
                    return f"data:{img.file_type};base64,{base64_data}"
                except Exception as e:
                    print(f"Error processing image: {e}")
        return None

    # Tempelkan hasil URL ke atribut dinamis agar mudah dipanggil di HTML
    users.profile_image_url = get_profile_image_url(users)
    
    return render_template('profile-user.html', user=users)


@app.route('/edit-profile-user/<int:user_id>', methods=['POST'])
@login_required
def edit_profile_user(user_id):
    if current_user.id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # --- 1. Update Data Teks ---
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.phone_number = request.form.get('phone_number')
        current_user.address = request.form.get('address')
        current_user.gender = request.form.get('gender')
        
        birth_date = request.form.get('birth_date')
        if birth_date:
            current_user.birth_date = datetime.strptime(birth_date, '%Y-%m-%d')

        # --- 2. Update/Upload Foto Profil ---
        if 'profile_photo' in request.files:
            file = request.files['profile_photo']
            if file and file.filename != '':
                # Baca data file
                file_data = file.read()
                file_name = file.filename
                file_type = file.content_type  # misal: image/jpeg
                file_size = len(file_data)

                # Cari apakah user sudah punya foto sebelumnya
                existing_img = db.session.query(ImageUsers).filter_by(user_id=user_id).first()

                if existing_img:
                    # Update foto lama
                    existing_img.file_data = file_data
                    existing_img.file_name = file_name
                    existing_img.file_type = file_type
                    existing_img.file_size = file_size
                else:
                    # Buat record foto baru
                    new_img = ImageUsers(
                        user_id=user_id,
                        file_data=file_data,
                        file_name=file_name,
                        file_type=file_type,
                        file_size=file_size
                    )
                    db.session.add(new_img)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Profil dan foto berhasil diperbarui!'}), 200
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
        

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)