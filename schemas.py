from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date, datetime

# User Schemas
class UserBase(BaseModel):
    username: Optional[str] = None
    email: str
    role: str = "customer" # 'patient', 'doctor', 'customer', 'admin'
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None

class UserCreate(UserBase):
    password: str

class User(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Patient Schemas
class PatientBase(BaseModel):
    name: str
    sex: Optional[str] = None
    age: Optional[int] = None
    dob: Optional[date] = None
    user_id: Optional[int] = None

class PatientCreate(PatientBase):
    pass

class Patient(PatientBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Tumor Marker Schemas
class TumorMarkerBase(BaseModel):
    psa: Optional[float] = None
    cea: Optional[float] = None
    ca153: Optional[float] = None
    afp: Optional[float] = None
    hpv: Optional[str] = None
    ctcs: Optional[float] = None
    pca3: Optional[float] = None
    dlx1: Optional[str] = None

class TumorMarkerCreate(TumorMarkerBase):
    pass

class TumorMarker(TumorMarkerBase):
    id: int
    report_id: int

    model_config = ConfigDict(from_attributes=True)


# Genetic Mutation Schemas
class GeneticMutationBase(BaseModel):
    exon20: Optional[float] = None
    g719x: Optional[float] = None
    exon19: Optional[float] = None
    l858r: Optional[float] = None

class GeneticMutationCreate(GeneticMutationBase):
    pass

class GeneticMutation(GeneticMutationBase):
    id: int
    report_id: int

    model_config = ConfigDict(from_attributes=True)


# Medical Report Schemas
class MedicalReportBase(BaseModel):
    doctor_id: Optional[int] = None
    specimen1: Optional[str] = None
    specimen2: Optional[str] = None
    collecting_date: Optional[date] = None
    receiving_date: Optional[date] = None
    testing_date: Optional[date] = None

class MedicalReportCreate(MedicalReportBase):
    patient: PatientCreate
    markers: TumorMarkerCreate
    genetics: GeneticMutationCreate

class MedicalReport(MedicalReportBase):
    id: int
    patient_id: int
    created_at: datetime
    updated_at: datetime
    patient: Patient
    markers: Optional[TumorMarker] = None
    genetics: Optional[GeneticMutation] = None

    model_config = ConfigDict(from_attributes=True)


# Product Schemas
class ProductBase(BaseModel):
    name: str
    sku: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    stock_quantity: int = 0
    category: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Order Item Schemas
class OrderItemBase(BaseModel):
    product_id: Optional[int] = None
    product_name: str
    price: float
    quantity: int

class OrderItemCreate(OrderItemBase):
    pass

class OrderItem(OrderItemBase):
    id: int
    order_id: int

    model_config = ConfigDict(from_attributes=True)


# Payment Transaction Schemas
class PaymentTransactionBase(BaseModel):
    order_id: int
    gateway: str
    transaction_ref: str
    amount: float
    currency: str = "THB"
    status: str
    payment_method: Optional[str] = None
    raw_response: Optional[str] = None

class PaymentTransactionCreate(PaymentTransactionBase):
    pass

class PaymentTransaction(PaymentTransactionBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Order Schemas
class OrderBase(BaseModel):
    user_id: Optional[int] = None
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    shipping_address: str
    payment_method: str

class OrderCreate(OrderBase):
    items: List[OrderItemCreate]

class OrderStatusUpdate(BaseModel):
    payment_status: Optional[str] = None
    order_status: Optional[str] = None

class Order(OrderBase):
    id: int
    payment_status: str
    order_status: str
    total_amount: float
    created_at: datetime
    updated_at: datetime
    items: List[OrderItem]
    transactions: List[PaymentTransaction] = []

    model_config = ConfigDict(from_attributes=True)


# Xzense Analysis Schemas
class XzenseAnalysisBase(BaseModel):
    title: str
    measurement_type: str # 'single' or 'dual'
    file1_name: str
    file1_data: str # JSON string of relative_time & resonance_frequency
    file2_name: Optional[str] = None
    file2_data: Optional[str] = None
    selected_time_start: Optional[float] = None
    selected_time_end: Optional[float] = None
    avg_frequency1: Optional[float] = None
    avg_frequency2: Optional[float] = None
    delta_f: Optional[float] = None

class XzenseAnalysisCreate(XzenseAnalysisBase):
    pass

class XzenseAnalysis(XzenseAnalysisBase):
    id: int
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Lab Registration Schemas
class LabRegistrationBase(BaseModel):
    course_id: str
    status: str = "pending" # 'pending', 'confirmed', 'completed', 'cancelled'

class LabRegistrationCreate(LabRegistrationBase):
    pass

class LabRegistration(LabRegistrationBase):
    id: int
    user_id: int
    registration_date: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
