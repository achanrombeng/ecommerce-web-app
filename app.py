from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from models import Product, User, db
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

@app.route('/admin/products')
@login_required
def admin_products():
    return render_template('admin_produk.html')

@app.route('/admin/add-product', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if request.method == 'POST':
        try:
            product_name = request.form.get('product_name')
            product_description = request.form.get('product_description')
            product_category = request.form.get('product_category')
            product_price = request.form.get('product_price')
            product_stock = request.form.get('product_stock')
            product_status = request.form.get('product_status', 'available')

             # Handle upload gambar menjadi base64
            product_image = None
            if 'product_image' in request.files:
                image_file = request.files['product_image']
                if image_file and image_file.filename != '':
                    # Validasi tipe file
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in image_file.filename and \
                       image_file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        
                        # Baca file dan konversi ke base64
                        import base64
                        
                        # Baca file sebagai binary
                        image_data = image_file.read()
                        
                        # Encode ke base64
                        base64_encoded = base64.b64encode(image_data).decode('utf-8')
                        
                        # Dapatkan content type
                        from werkzeug.utils import secure_filename
                        filename = secure_filename(image_file.filename)
                        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'jpeg'
                        
                        # Mapping extension ke MIME type
                        mime_types = {
                            'png': 'image/png',
                            'jpg': 'image/jpeg',
                            'jpeg': 'image/jpeg',
                            'gif': 'image/gif',
                            'webp': 'image/webp'
                        }
                        
                        mime_type = mime_types.get(file_extension, 'image/jpeg')
                        
                        # Format base64 string untuk disimpan di database
                        product_image = f"data:{mime_type};base64,{base64_encoded}"
                        
                        # Validasi ukuran file (max 5MB)
                        if len(image_data) > 5 * 1024 * 1024:
                            flash('Ukuran gambar terlalu besar. Maksimal 5MB.', 'error')
                            return render_template('admin_add_produk.html')
                    else:
                        flash('Format file tidak didukung. Gunakan PNG, JPG, JPEG, GIF, atau WebP.', 'error')
                        return render_template('admin_add_produk.html')

            # Validasi data wajib
            if not product_name or not product_price:
                flash('Nama produk dan harga harus diisi!', 'error')
                return render_template('admin_add_produk.html')
            
              # Konversi tipe data
            try:
                product_price = int(product_price)
                product_stock = int(product_stock) if product_stock else 0
            except ValueError:
                flash('Harga dan stok harus berupa angka!', 'error')
                return render_template('admin_add_produk.html')

            # Buat product baru
            new_product = Product(
                product_name=product_name,
                product_description=product_description,
                product_category=product_category,
                product_price=product_price,
                product_stock=product_stock,
                product_status=product_status,
                product_image=product_image,
                created_at=datetime.now()
            )

            db.session.add(new_product)
            db.session.commit()

            flash('Produk berhasil ditambahkan!', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding product: {e}")
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
@app.route('/produk-user')
def produk_user():
    return render_template('produk-user.html')

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