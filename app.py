from datetime import datetime
import traceback
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
import magic
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from models import Image, Product, User, db
import os
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
            role='user'  # tambahkan ini
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
    return render_template('dashboard.html', user=current_user)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    
    users = db.session.query(User).all()
    return render_template('admin_dashboard.html', users=users)

from sqlalchemy import func

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
def admin_products():
    if request.method == 'POST':
        try:
            print("\n" + "=" * 60)
            print("POST REQUEST RECEIVED")
            print("=" * 60)
            
            # Ambil parameter filter dari request
            name_filter = request.form.get('name', '').strip()
            category_filter = request.form.get('category', '').strip()
            max_price_filter = request.form.get('maxPrice', '').strip()
            status_filter = request.form.get('status', '').strip()
            
            print(f"Filters:")
            print(f"  Name: '{name_filter}'")
            print(f"  Category: '{category_filter}'")
            print(f"  MaxPrice: '{max_price_filter}'")
            print(f"  Status: '{status_filter}'")
            
            # Query database dengan filter
            query = db.session.query(Product)
            
            # Debug: Cek total sebelum filter
            total_in_db = query.count()
            print(f"\nTotal products in database: {total_in_db}")
            
            if total_in_db == 0:
                print("⚠️  WARNING: Database is EMPTY!")
                return jsonify({'data': []})
            
            # Apply filters
            if name_filter:
                query = query.filter(func.lower(Product.product_name).like(f'%{name_filter.lower()}%'))
                print(f"  After name filter: {query.count()} products")
            
            if category_filter:
                query = query.filter(func.lower(Product.product_category).like(f'%{category_filter.lower()}%'))
                print(f"  After category filter: {query.count()} products")
            
            if max_price_filter:
                try:
                    max_price = float(max_price_filter)
                    query = query.filter(Product.product_price <= max_price)
                    print(f"  After price filter (<= {max_price}): {query.count()} products")
                except ValueError:
                    print(f"  Invalid price: {max_price_filter}")
            
            # Filter status - BOOLEAN bukan string!
            if status_filter:
                if status_filter.lower() == 'aktif':
                    query = query.filter(Product.product_status == True)
                    print(f"  After status filter (True): {query.count()} products")
                elif status_filter.lower() == 'nonaktif':
                    query = query.filter(Product.product_status == False)
                    print(f"  After status filter (False): {query.count()} products")
            
            # Get results
            products = query.order_by(Product.id.desc()).all()
            
            print(f"\n✓ Found {len(products)} products after all filters")
            
            # Format data untuk DataTables
            data = []
            for i, product in enumerate(products):
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
                
                product_data = {
                    'product_id': product.id,
                    'product_name': product.product_name,
                    'product_category': product.product_category or 'Tidak ada kategori',
                    'product_price': product.product_price,
                    'product_status': display_status
                }
                data.append(product_data)
                
                # Print first 2 products as sample
                if i < 2:
                    print(f"\nSample Product #{i+1}:")
                    print(f"  ID: {product.id}")
                    print(f"  Name: {product.product_name}")
                    print(f"  Category: {product.product_category}")
                    print(f"  Price: {product.product_price}")
                    print(f"  Stock: {product.product_stock}")
                    print(f"  Status (Boolean): {product.product_status}")
                    print(f"  Status Display: {display_status}")
            
            response_data = {'data': data}
            print(f"\n✓ Sending response with {len(data)} products")
            print("=" * 60 + "\n")
            
            return jsonify(response_data)
            
        except Exception as e:
            print("\n" + "!" * 60)
            print("ERROR in POST request:")
            print("!" * 60)
            print(traceback.format_exc())
            print("!" * 60 + "\n")
            return jsonify({
                'data': [],
                'error': str(e)
            }), 500
    
    # GET request - tampilkan halaman
    try:
        print("\n" + "=" * 60)
        print("GET REQUEST - Loading Page")
        print("=" * 60)
        
        # Hitung statistik
        total_products = db.session.query(Product).count()
        print(f"Total products: {total_products}")
        
        # Produk aktif (status = True)
        active_products = db.session.query(Product).filter(
            Product.product_status == True
        ).count()
        print(f"Active products (status=True): {active_products}")
        
        # Stok menipis (stok < 10 dan > 0)
        low_stock = db.session.query(Product).filter(
            Product.product_stock < 10,
            Product.product_stock > 0
        ).count()
        print(f"Low stock: {low_stock}")
        
        # Habis stok (stok = 0)
        out_of_stock = db.session.query(Product).filter(
            Product.product_stock == 0
        ).count()
        print(f"Out of stock: {out_of_stock}")
        
        print("=" * 60 + "\n")
        
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
        print("\n" + "!" * 60)
        print("ERROR in GET request:")
        print("!" * 60)
        print(traceback.format_exc())
        print("!" * 60 + "\n")
        return f"Error: {str(e)}", 500
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

@app.route('/admin/edit-product', methods=['GET', 'POST'])
@login_required
def admin_edit_product():
    return render_template('admin_edit_produk.html')

@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin_order.html')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin():
        flash('Akses ditolak! Halaman ini hanya untuk admin.', 'error')
        return redirect(url_for('dashboard'))
    users = db.session.query(User).all()
    return render_template('admin_user.html', users=users)

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
    
@app.route('/form-order-user')
@login_required
def form_order_user():
    return render_template('form_order_user.html')

@app.route('/order-user')
def order_user():
    return render_template('order-user.html')

@app.route('/profile-user' , methods=['GET'])
def profile_user():
    return render_template('profile-user.html')

@app.route('/edit-profile-user', methods=['POST'])
@login_required
def edit_profile_user():
    try:
        # Ambil data dari form
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            email = request.form.get('email')
            phone_number = request.form.get('phone_number')
            birth_date = request.form.get('birth_date')
            gender = request.form.get('gender')
            address = request.form.get('address')
            
            # Update data user
            current_user.first_name = first_name
            current_user.last_name = last_name
            current_user.email = email
            current_user.phone_number = phone_number
            current_user.address = address
            current_user.gender = gender
            
            # Handle birth date conversion
            if birth_date:
                current_user.birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()

            
            # Commit perubahan ke database
            db.session.commit()

            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile_user'))
            
    except Exception as e:
        db.session.rollback()
        print(f"Error updating profile: {e}")
        flash('Error updating profile: ' + str(e), 'error')
    
    return render_template('profile-user.html')
        

    

if __name__ == '__main__':
    app.run(debug=True)