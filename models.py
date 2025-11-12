from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, ForeignKey, Integer, LargeBinary, String, DateTime, Boolean, Text
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin


Base = declarative_base()
db = SQLAlchemy()
class User(Base, UserMixin):
    __tablename__ = 'users_db'
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    phone_number = Column(String(20), nullable=True)  # Tambahkan
    address = Column(Text, nullable=True)  # Tambahkan
    gender = Column(String(10), nullable=True)  # Tambahkan
    role = Column(String(20), default='user')
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    birth_date = Column(DateTime, nullable=True)  # Tambahkan

    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user is admin"""
        return self.role == 'admin'
    

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.email}>'
    
class Product(Base):
    __tablename__ = 'product_db'
    id = Column(Integer, primary_key=True)
    product_name = Column(String(100), nullable=False)
    product_description = Column(Text, nullable=True)
    product_category = Column(String(50), nullable=True)
    product_price = Column(Integer, nullable=False)
    product_stock = Column(Integer, default=0)
    product_status = Column(Boolean, default=True)  # Fixed: removed (20)
    created_at = Column(DateTime, default=datetime.now)
    
    # Hanya satu relationship yang menggunakan backref
    images = relationship("Image", backref="product", cascade="all, delete-orphan")

class Image(Base):
    __tablename__ = "image_product_db"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('product_db.id', ondelete='CASCADE'))
    file_data = Column(LargeBinary)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)


class Order(Base):
    __tablename__ = 'order_db'
    id = Column(Integer, primary_key=True)
    User_id = Column(Integer, ForeignKey('users_db.id'))
    created_at = Column(DateTime, default=datetime.now)
    amount = Column(Integer, nullable=False)

    user = relationship("User", backref="orders")

    def __repr__(self):
        return f'<Order {self.id} - User {self.user_id}>'
    
class ProductOrder(Base):
    __tablename__ = 'product_order_db'
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('product_db.id'))
    order_id = Column(Integer, ForeignKey('order_db.id'))
    quantity = Column(Integer, nullable=False)

    product = relationship("Product", backref="product_orders")
    order = relationship("Order", backref="product_orders")