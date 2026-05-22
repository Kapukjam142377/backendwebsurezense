from sqlalchemy import Column, Integer, String, Date, ForeignKey, Numeric, DateTime, Boolean, Text, func
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="customer") # 'patient', 'doctor', 'customer', 'admin'
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    orders = relationship("Order", back_populates="user")
    patients = relationship("Patient", back_populates="user")
    reports = relationship("MedicalReport", back_populates="doctor")
    analyses = relationship("XzenseAnalysis", back_populates="user")
    registrations = relationship("LabRegistration", back_populates="user")

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    sex = Column(String(50))
    age = Column(Integer)
    dob = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="patients")
    # Cascading deletes will remove associated reports if a patient is deleted
    reports = relationship("MedicalReport", back_populates="patient", cascade="all, delete-orphan")

class MedicalReport(Base):
    __tablename__ = "medical_reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id", ondelete="CASCADE"))
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    specimen1 = Column(String(100))
    specimen2 = Column(String(100))
    collecting_date = Column(Date)
    receiving_date = Column(Date)
    testing_date = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    patient = relationship("Patient", back_populates="reports")
    doctor = relationship("User", back_populates="reports")
    markers = relationship("TumorMarker", back_populates="report", uselist=False, cascade="all, delete-orphan")
    genetics = relationship("GeneticMutation", back_populates="report", uselist=False, cascade="all, delete-orphan")

class TumorMarker(Base):
    __tablename__ = "tumor_markers"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("medical_reports.id", ondelete="CASCADE"), unique=True)
    psa = Column(Numeric(10, 2))
    cea = Column(Numeric(10, 2))
    ca153 = Column(Numeric(10, 2))
    afp = Column(Numeric(10, 2))
    hpv = Column(String(100))
    ctcs = Column(Numeric(10, 2))
    pca3 = Column(Numeric(10, 2))
    dlx1 = Column(String(100))

    report = relationship("MedicalReport", back_populates="markers")

class GeneticMutation(Base):
    __tablename__ = "genetic_mutations"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(Integer, ForeignKey("medical_reports.id", ondelete="CASCADE"), unique=True)
    exon20 = Column(Numeric(10, 2))
    g719x = Column(Numeric(10, 2))
    exon19 = Column(Numeric(10, 2))
    l858r = Column(Numeric(10, 2))

    report = relationship("MedicalReport", back_populates="genetics")

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False, default=0.00)
    image_url = Column(String(500), nullable=True)
    stock_quantity = Column(Integer, default=0)
    category = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    order_items = relationship("OrderItem", back_populates="product")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    shipping_address = Column(String(1000), nullable=False)
    payment_method = Column(String(100), nullable=False)
    payment_status = Column(String(50), default="pending")
    order_status = Column(String(50), default="received")
    total_amount = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    transactions = relationship("PaymentTransaction", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")

class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    gateway = Column(String(50), nullable=False) # e.g. 'OPN', '2C2P', 'WooCommerce'
    transaction_ref = Column(String(255), unique=True, index=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default="THB")
    status = Column(String(50), nullable=False) # e.g. 'success', 'pending', 'failed', 'refunded'
    payment_method = Column(String(50), nullable=True)
    raw_response = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    order = relationship("Order", back_populates="transactions")

class XzenseAnalysis(Base):
    __tablename__ = "xzense_analyses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    measurement_type = Column(String(20), nullable=False) # 'single' or 'dual'
    file1_name = Column(String(255), nullable=False)
    file1_data = Column(Text, nullable=False) # Stored as JSON string
    file2_name = Column(String(255), nullable=True)
    file2_data = Column(Text, nullable=True) # Stored as JSON string
    selected_time_start = Column(Numeric(12, 4), nullable=True)
    selected_time_end = Column(Numeric(12, 4), nullable=True)
    avg_frequency1 = Column(Numeric(15, 4), nullable=True)
    avg_frequency2 = Column(Numeric(15, 4), nullable=True)
    delta_f = Column(Numeric(15, 4), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="analyses")

class LabRegistration(Base):
    __tablename__ = "lab_registrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(String(100), nullable=False)
    status = Column(String(50), default="pending") # 'pending', 'confirmed', 'completed', 'cancelled'
    registration_date = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="registrations")
