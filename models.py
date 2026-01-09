from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, ForeignKey, Integer, LargeBinary, String, DateTime, Boolean, Text, Enum
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import enum

Base = declarative_base()
db = SQLAlchemy()
class PaymentMethodEnum(str,enum.Enum):
    TRANSFER_BANK = "TRANSFER_BANK"
    COD = "COD"

class OrderStatusEnum(str,enum.Enum):
    PENDING = "PENDING"
    APPROVE = "APPROVE"
    CANCEL = "CANCEL"

class RoleEnum(str,enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class GenderEnum(str,enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
class User(Base, UserMixin):
    __tablename__ = 'users_db'
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    phone_number = Column(String(20), nullable=True)  
    address = Column(Text, nullable=True)  
    gender = Column(Enum(GenderEnum,native_enum=False,validate_strings=True),default=GenderEnum.OTHER,nullable=True)  
    role = Column(Enum(RoleEnum,native_enum=False,validate_strings=True),default=RoleEnum.USER,nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    birth_date = Column(DateTime, nullable=True)  

    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """Check if user is admin"""
        return self.role == RoleEnum.ADMIN
    

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

class Cart(Base):
    __tablename__ = 'cart_db'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users_db.id'))
    product_id = Column(Integer, ForeignKey('product_db.id'))
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", backref="carts")
    product = relationship("Product", backref="carts")

class Order(Base):
    __tablename__ = 'order_db'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users_db.id'))
    created_at = Column(DateTime, default=datetime.now)
    amount = Column(Integer, nullable=False)
    payment_method = Column(Enum(PaymentMethodEnum,native_enum=False,validate_strings=True),nullable=False)
    notes = Column(String(255), nullable=True)
    status = Column(
    Enum(OrderStatusEnum, native_enum=False, validate_strings=True),
    default=OrderStatusEnum.PENDING,
    nullable=False
)
    user = relationship("User", backref="orders")
    products_ordered = relationship("Product", secondary='product_order_db', backref="orders")

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