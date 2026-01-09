from datetime import datetime
import traceback
from venv import logger
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import GenderEnum, Image, Order, OrderStatusEnum, PaymentMethodEnum, Product, ProductOrder, RoleEnum, User, db, Cart
import os
import base64
from dotenv import load_dotenv

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

import base64

# Tambahkan baris ini agar Jinja2 mengenali filter b64encode
@app.template_filter('b64encode')
def b64encode_filter(data):
    if data:
        return base64.b64encode(data).decode('utf-8')
    return ""

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).filter_by(id=user_id).first()

@app.route('/')
def index():
    return redirect(url_for('login'))

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

@app.route('/dashboard')
@login_required
def dashboard():
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
                         user=current_user, 
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
    
    users = db.session.query(User).all()
    return render_template('admin_dashboard.html', users=users, total_admins=total_admins, total_users=total_users, total_products=total_products, orders=orders)

from sqlalchemy import func

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
def admin_products():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        try:
            # Ambil parameter filter dari request
            name_filter = request.form.get('name', '').strip()
            category_filter = request.form.get('category', '').strip()
            max_price_filter = request.form.get('maxPrice', '').strip()
            status_filter = request.form.get('status', '').strip()
            
            # Query database dengan filter
            query = db.session.query(Product)
            
            # Apply filters
            if name_filter:
                query = query.filter(func.lower(Product.product_name).like(f'%{name_filter.lower()}%'))
            
            if category_filter:
                query = query.filter(func.lower(Product.product_category).like(f'%{category_filter.lower()}%'))
            
            if max_price_filter:
                try:
                    max_price = float(max_price_filter)
                    # Konversi product_price ke float untuk filter
                    query = query.filter(func.cast(Product.product_price, Float) <= max_price)
                except ValueError:
                    pass  # Ignore invalid price filter
            
            # Filter status
            if status_filter:
                if status_filter.lower() == 'aktif':
                    query = query.filter(Product.product_status == True)
                elif status_filter.lower() == 'nonaktif':
                    query = query.filter(Product.product_status == False)
            
            # Get results
            products = query.order_by(Product.id.desc()).all()
            
            # Format data untuk DataTables
            data = []
            for product in products:
                # Konversi status Boolean ke display string
                if product.product_status == True:
                    display_status = 'Available'
                elif product.product_status == False:
                    display_status = 'Unavailable'
                else:
                    display_status = 'Unknown'
                
                # Override jika stok habis
                if product.product_stock == 0:
                    display_status = 'Out Of Stock'
                
                # Format harga - pastikan product_price berupa string yang valid
                try:
                    # Jika product_price sudah string angka, konversi ke int/float dulu
                    if isinstance(product.product_price, str):
                        # Hapus karakter non-numerik jika ada
                        price_str = ''.join(c for c in product.product_price if c.isdigit() or c == '.')
                        if price_str:
                            price_value = float(price_str)
                        else:
                            price_value = 0
                    else:
                        price_value = float(product.product_price)
                    
                    price_formatted = f"{price_value:,.0f}"
                except (ValueError, TypeError):
                    price_formatted = "0"
                
                product_data = {
                    'product_id': product.id,
                    'product_name': product.product_name,
                    'product_category': product.product_category or 'Tidak ada kategori',
                    'product_price': price_formatted,
                    'product_stock': product.product_stock,
                    'product_status': display_status
                }
                data.append(product_data)
            
            return jsonify({'data': data})
            
        except Exception as e:
            app.logger.error(f"Error in POST request: {str(e)}")
            return jsonify({'data': [], 'error': str(e)}), 500
    
    # GET request - tampilkan halaman
    try:
        # Hitung statistik
        total_products = db.session.query(Product).count()
        
        # Produk aktif
        active_products = db.session.query(Product).filter(
            Product.product_status == True
        ).count()
        
        # Stok menipis
        low_stock = db.session.query(Product).filter(
            Product.product_stock < 10,
            Product.product_stock > 0
        ).count()
        
        # Habis stok
        out_of_stock = db.session.query(Product).filter(
            Product.product_stock == 0
        ).count()
        
        # Permission check
        can_update = True
        can_delete = True
        
        return render_template('admin_produk.html',
                             total_products=total_products,
                             active_products=active_products,
                             low_stock=low_stock,
                             out_of_stock=out_of_stock,
                             can_update=can_update,
                             can_delete=can_delete)
                             
    except Exception as e:
        app.logger.error(f"Error in GET request: {str(e)}")
        flash(f'Terjadi kesalahan: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
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
    
    return render_template('admin_add_produk.html') 

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

from flask import jsonify, request
from datetime import datetime

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
    
    # Handle POST request untuk DataTables AJAX
    if request.method == 'POST':
        # Ambil filter dari request
        customer_filter = request.form.get('customer', '').strip()
        date_filter = request.form.get('date', '').strip()
        max_amount = request.form.get('maxAmount', '').strip()
        status_filter = request.form.get('status', '').strip()
        
        # Query orders dengan joins
        query = db.session.query(Order).options(
            joinedload(Order.product_orders).joinedload(ProductOrder.product),
            joinedload(Order.user)
        )
        
        # Apply filters
        if customer_filter:
            query = query.join(Order.user).filter(
                db.or_(
                    User.first_name.ilike(f'%{customer_filter}%'),
                    User.last_name.ilike(f'%{customer_filter}%'),
                    User.email.ilike(f'%{customer_filter}%')
                )
            )
        
        if date_filter:
            # Filter by date (assuming created_at is datetime)
            from datetime import datetime
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
            # Sesuaikan dengan Enum Anda
            if status_filter.lower() == 'pending':
                query = query.filter(Order.status == OrderStatusEnum.PENDING)
            elif status_filter.lower() == 'approve':
                query = query.filter(Order.status == OrderStatusEnum.APPROVE)
            elif status_filter.lower() == 'cancel':
                query = query.filter(Order.status == OrderStatusEnum.CANCEL)
        
        orders = query.order_by(Order.created_at.desc()).all()
        
        # Format data untuk DataTables
        data = []
        for order in orders:
            # Hitung total items
            total_items = sum((po.quantity or 0) for po in order.product_orders)
            
            # Format amount
            amount_formatted = "{:,.0f}".format(order.amount or 0)
            
            # Customer info
            customer_name = f"{order.user.first_name} {order.user.last_name}"
            customer_avatar = f"https://ui-avatars.com/api/?name={order.user.first_name}+{order.user.last_name}"
            
            data.append({
                'id': order.id,
                'total_items': total_items,
                'customer_name': customer_name,
                'customer_email': order.user.email,
                'customer_avatar': customer_avatar,
                'created_at': order.created_at.isoformat(),
                'date': order.created_at.strftime("%d %B %Y"),
                'time': order.created_at.strftime("%H:%M"),
                'amount': amount_formatted,
                'payment_method': order.payment_method.value if order.payment_method else '-',
                'status': order.status.value if hasattr(order.status, 'value') else str(order.status)
            })
        
        return jsonify({'data': data})
    
    # Handle GET request - render template
    orders = db.session.query(Order).options(
        joinedload(Order.product_orders).joinedload(ProductOrder.product),
        joinedload(Order.user)
    ).order_by(Order.created_at.desc()).all()
    
    pending = sum(1 for order in orders if order.status == OrderStatusEnum.PENDING)
    approved = sum(1 for order in orders if order.status == OrderStatusEnum.APPROVE)
    cancel = sum(1 for order in orders if order.status == OrderStatusEnum.CANCEL)
    
    return render_template('admin_order.html', 
                         orders=orders, 
                         pending=pending, 
                         approved=approved, 
                         cancel=cancel,
                         can_update=True)
@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # Ambil filter dari request AJAX
        name_filter = request.form.get('name', '').strip()
        email_filter = request.form.get('email', '').strip()
        role_filter = request.form.get('role', '').strip()
        gender_filter = request.form.get('gender', '').strip()
        
        query = db.session.query(User)
        
        # Logika Filtering
        if name_filter:
            query = query.filter(User.first_name.ilike(f'%{name_filter}%'))
        if email_filter:
            query = query.filter(User.email.ilike(f'%{email_filter}%'))
        if role_filter:
            query = query.filter(User.role == role_filter.upper())
        if gender_filter:
            query = query.filter(User.gender == gender_filter.upper())
        
        users = query.all()
        
        # Format data untuk DataTables
        data = []
        for user in users:
            # Mengambil URL profil atau None
            # Pastikan field 'profile_picture' ada di Model User Anda
            p_pic = getattr(user, 'profile_picture', None)
            
            data.append({
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name or '',
                'email': user.email,
                'role': user.role.value if hasattr(user.role, 'value') else str(user.role),
                'gender': user.gender.value if hasattr(user.gender, 'value') else str(user.gender),
                'birth_date': user.birth_date.strftime("%d %B %Y") if user.birth_date else '-',
                'profile_picture': p_pic
            })
        
        return jsonify({'data': data})
    
    # Untuk GET request awal
    users_all = db.session.query(User).all()
    total_admins = len([u for u in users_all if u.role == 'ADMIN' or (hasattr(u.role, 'value') and u.role.value == 'ADMIN')])
    total_users = len(users_all) - total_admins
    
    return render_template('admin_user.html', 
                         users=users_all, 
                         total_admins=total_admins, 
                         total_users=total_users,
                         can_update=True)

@app.route('/admin/add-user', methods=['GET', 'POST'])
@login_required
def admin_add_user():
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
    return render_template('admin_add_user.html')

@app.route('/admin/edit-user')
@login_required
def admin_edit_user():
    user = db.session.query(User).filter_by(id=request.args.get('user_id')).first()
    return render_template('admin_edit_user.html', user=user)


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
                # Baca file dan ubah ke Base64 (atau simpan ke folder sesuai struktur Anda)
                image_data = file.read()
                # Jika Anda menyimpan sebagai string base64 di database:
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
        
        return render_template('produk-user.html', products=processed_products)
        
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
    
@app.route('/form-order-user', methods=['GET', 'POST'])
@login_required
def form_order_user():
    user_data = db.session.query(User).filter_by(id=current_user.id).first()
    product_now = db.session.query(Product).filter_by(id=request.args.get('product_id')).first()
    if request.method == 'POST':
        try:
            product_id = request.form.get('product_id')
            quantity = int(request.form.get('quantity', 1))
            
            product = db.session.query(Product).filter_by(id=product_id).first()
            if not product:
                flash('Produk tidak ditemukan!', 'error')
                return redirect(url_for('produk_user'))
            
            if product.product_stock < quantity:
                flash('Stok produk tidak mencukupi!', 'error')
                return redirect(url_for('form_order_user', product_id=product_id))
            
            # Buat order baru
            new_order = Order(
                user_id=current_user.id,
                created_at=datetime.now(),
                amount=product.product_price * quantity
            )
            db.session.add(new_order)
            db.session.commit()
            
            # Tambah produk ke order
            product_order = ProductOrder(
                product_id=product.id,
                order_id=new_order.id,
                quantity=quantity
            )
            db.session.add(product_order)
            
            # Update stok produk
            product.product_stock -= quantity
            
            db.session.commit()
            
            flash('Order berhasil dibuat!', 'success')
            return redirect(url_for('order_user'))
        except Exception as e:
            db.session.rollback()
            print(f"Error creating order: {e}")
            import traceback
            traceback.print_exc()
            flash('Error membuat order: ' + str(e), 'error')


    return render_template('form_order_user.html', user_data=user_data, product_now=product_now)

@app.route('/api/store', methods=['POST'])
@login_required
def store_data():
    try:
        if not request.is_json:
            return jsonify({'success': False, 'message': 'JSON required'}), 400

        data = request.get_json()

        required = ['productId', 'quantity', 'payment']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'message': f'Field wajib: {", ".join(missing)}'
            }), 400

        
        product = db.session.query(Product).filter_by(id=data['productId']).first()
        if not product:
            return jsonify({'success': False, 'message': 'Produk tidak ditemukan'}), 404

        quantity = int(data['quantity'])
        if quantity < 1:
            return jsonify({'success': False, 'message': 'Quantity minimal 1'}), 400
        if quantity > product.product_stock:
            return jsonify({'success': False, 'message': 'Stok produk tidak mencukupi'}), 400
        
        

        payment_method = PaymentMethodEnum(data['payment'])

        total_amount = int(product.product_price) * int(quantity)
        print(f"Debug: total_amount calculated as {total_amount}")

        new_order = Order(
            user_id=current_user.id,
            user=current_user,
            products_ordered=[product],
            amount=total_amount,
            payment_method=payment_method,
            status=OrderStatusEnum.PENDING,
            notes=data.get('notes', '')
        )

        db.session.add(new_order)
        db.session.flush()

        product_order = ProductOrder(
            product_id=product.id,
            order_id=new_order.id,
            quantity=quantity
        )

        db.session.add(product_order)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Order berhasil dibuat',
            'order_id': new_order.id
        }), 201

    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Metode pembayaran tidak valid'
        }), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Terjadi kesalahan: {str(e)}'
        }), 500


@app.route('/order-user')
@login_required
def order_user():
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
        
    return render_template('order-user.html', orders=orders)
@app.route('/add-to-cart', methods=['POST'])
@login_required
def add_to_cart():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    product = db.session.query(Product).filter_by(id=product_id).first()
    if not product:
        flash('Produk tidak ditemukan!', 'error')
        return redirect(url_for('produk_user'))
    if product.product_stock < quantity:
        flash('Stok produk tidak mencukupi!', 'error')
        return redirect(url_for('produk_user'))
    product.product_stock -= quantity
    db.session.commit()
    return redirect(url_for('produk_user'))

@app.route('/cart-user')
def cart_user():
    # Mengampil data cart dari user saat ini
    # cart = db.session.query(Cart).filter_by(user_id=current_user.id).all()
    return render_template('cart-user.html')

@app.route('/profile-user' , methods=['GET'])
def profile_user():
    return render_template('profile-user.html')

from flask import jsonify # Pastikan jsonify diimport

@app.route('/edit-profile-user/<int:user_id>', methods=['POST'])
@login_required
def edit_profile_user(user_id):
    # Pastikan hanya user yang bersangkutan yang bisa edit profilenya sendiri
    if current_user.id != user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        # Ambil data dari form
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        phone_number = request.form.get('phone_number')
        birth_date = request.form.get('birth_date')
        gender = request.form.get('gender')
        address = request.form.get('address')
        
        # Update data user
        current_user.first_name = first_name
        current_user.last_name = last_name
        current_user.phone_number = phone_number
        current_user.address = address
        current_user.gender = gender # Pastikan kolom gender di DB menerima string 'MALE'/'FEMALE'
        
        # Handle birth date conversion
        if birth_date:
            try:
                current_user.birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Format tanggal lahir tidak valid'}), 400

        # Commit perubahan ke database
        db.session.commit()

        # Karena menggunakan fetch/AJAX, kita kirim respons JSON
        return jsonify({
            'success': True,
            'message': 'Profil berhasil diperbarui!'
        }), 200
            
    except Exception as e:
        db.session.rollback()
        print(f"Error updating profile: {e}")
        return jsonify({
            'success': False, 
            'message': f'Gagal memperbarui profil: {str(e)}'
        }), 500
        


  

if __name__ == '__main__':
    app.run(debug=True)