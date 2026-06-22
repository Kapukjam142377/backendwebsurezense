from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import hashlib
import secrets
import models
import schemas
from database import engine, get_db

# Create all database tables on startup (if they do not exist yet)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Surazense Cancer Report API",
    description="Backend API for Surazense Cancer Detection Diagnostic Reports",
    version="1.0.0"
)

# Configure Cross-Origin Resource Sharing (CORS)
# Allows the separate React frontend to securely request data from this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5000",
        "https://new-web-surazense.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging
    logging.exception(exc)
    
    headers = {}
    origin = request.headers.get("origin")
    if origin in [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5000",
        "https://new-web-surazense.vercel.app"
    ]:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "message": str(exc)},
        headers=headers
    )

@app.get("/", tags=["System Status"])
def read_root():
    return {
        "status": "online",
        "message": "Surazense Cancer Report API is running successfully!",
        "docs_url": "/docs"  # Auto-generated Swagger documentation path
    }

# 1. Create a Full Report (creates patient, report, markers, and genetics in a single transaction)
@app.post("/api/reports", response_model=schemas.MedicalReport, status_code=status.HTTP_201_CREATED, tags=["Medical Reports"])
def create_report(report_in: schemas.MedicalReportCreate, db: Session = Depends(get_db)):
    try:
        # Create Patient
        db_patient = models.Patient(
            name=report_in.patient.name,
            sex=report_in.patient.sex,
            age=report_in.patient.age,
            dob=report_in.patient.dob
        )
        db.add(db_patient)
        db.flush() # Flush to get generated db_patient.id

        # Create Medical Report
        db_report = models.MedicalReport(
            patient_id=db_patient.id,
            specimen1=report_in.specimen1,
            specimen2=report_in.specimen2,
            collecting_date=report_in.collecting_date,
            receiving_date=report_in.receiving_date,
            testing_date=report_in.testing_date
        )
        db.add(db_report)
        db.flush() # Flush to get generated db_report.id

        # Create Tumor Markers
        db_markers = models.TumorMarker(
            report_id=db_report.id,
            psa=report_in.markers.psa,
            cea=report_in.markers.cea,
            ca153=report_in.markers.ca153,
            afp=report_in.markers.afp,
            hpv=report_in.markers.hpv,
            ctcs=report_in.markers.ctcs,
            pca3=report_in.markers.pca3,
            dlx1=report_in.markers.dlx1
        )
        db.add(db_markers)

        # Create Genetic Mutations
        db_genetics = models.GeneticMutation(
            report_id=db_report.id,
            exon20=report_in.genetics.exon20,
            g719x=report_in.genetics.g719x,
            exon19=report_in.genetics.exon19,
            l858r=report_in.genetics.l858r
        )
        db.add(db_genetics)

        # Commit all entities as a atomic transaction
        db.commit()
        db.refresh(db_report)
        return db_report
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create report: {str(e)}"
        )

# 2. Get a Specific Report by ID (returns patient, markers, and genetics data)
@app.get("/api/reports/{report_id}", response_model=schemas.MedicalReport, tags=["Medical Reports"])
def get_report(report_id: int, db: Session = Depends(get_db)):
    db_report = db.query(models.MedicalReport).filter(models.MedicalReport.id == report_id).first()
    if not db_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    return db_report

# 3. List All Reports
@app.get("/api/reports", response_model=List[schemas.MedicalReport], tags=["Medical Reports"])
def list_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    reports = db.query(models.MedicalReport).offset(skip).limit(limit).all()
    return reports

# 4. Delete a Report (cascades delete to markers and genetics tables)
@app.delete("/api/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Medical Reports"])
def delete_report(report_id: int, db: Session = Depends(get_db)):
    db_report = db.query(models.MedicalReport).filter(models.MedicalReport.id == report_id).first()
    if not db_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    db.delete(db_report)
    db.commit()
    return None

# ===================================================
#   eCommerce Orders & Checkout API Endpoints
# ===================================================

# 1. Create Order (Checkout)
@app.post("/api/orders", response_model=schemas.Order, status_code=status.HTTP_201_CREATED, tags=["eCommerce Orders"])
def create_order(order_in: schemas.OrderCreate, db: Session = Depends(get_db)):
    try:
        # Calculate total price of all order items
        total_amount = sum(item.price * item.quantity for item in order_in.items)

        # Create Order Header
        db_order = models.Order(
            customer_name=order_in.customer_name,
            customer_email=order_in.customer_email,
            customer_phone=order_in.customer_phone,
            shipping_address=order_in.shipping_address,
            payment_method=order_in.payment_method,
            payment_status="pending",
            order_status="received",
            total_amount=total_amount
        )
        db.add(db_order)
        db.flush() # Flush to get db_order.id

        # Create Order Items
        for item in order_in.items:
            db_item = models.OrderItem(
                order_id=db_order.id,
                product_id=item.product_id,
                product_name=item.product_name,
                price=item.price,
                quantity=item.quantity
            )
            db.add(db_item)

        db.commit()
        db.refresh(db_order)
        return db_order
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to place order: {str(e)}"
        )

# 2. List All Orders
@app.get("/api/orders", response_model=List[schemas.Order], tags=["eCommerce Orders"])
def list_orders(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    orders = db.query(models.Order).offset(skip).limit(limit).all()
    return orders

# 3. Get Specific Order
@app.get("/api/orders/{order_id}", response_model=schemas.Order, tags=["eCommerce Orders"])
def get_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return db_order

# 4. Update Order / Payment Status
@app.patch("/api/orders/{order_id}/status", response_model=schemas.Order, tags=["eCommerce Orders"])
def update_order_status(order_id: int, status_update: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    
    if status_update.payment_status is not None:
        db_order.payment_status = status_update.payment_status
    if status_update.order_status is not None:
        db_order.order_status = status_update.order_status
        
    db.commit()
    db.refresh(db_order)
    return db_order

# 5. Delete / Cancel Order
@app.delete("/api/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["eCommerce Orders"])
def delete_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    db.delete(db_order)
    db.commit()
    return None


# ===================================================
#   Password Hashing Helpers
# ===================================================

def hash_password(password: str) -> str:
    # Generate a random 16-byte salt
    salt = secrets.token_hex(16)
    # Hash using PBKDF2 with SHA-256
    pwd_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # Number of iterations
    )
    # Store both salt and hash together, separated by a colon
    return f"{salt}:{pwd_hash.hex()}"

def verify_password(password: str, hashed_password_str: str) -> bool:
    try:
        salt, pwd_hash_hex = hashed_password_str.split(":")
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return pwd_hash.hex() == pwd_hash_hex
    except Exception:
        return False


# ===================================================
#   User Management API Endpoints
# ===================================================

class UserLogin(BaseModel):
    email: str
    password: str
    source_app: Optional[str] = None  # 'build' or 'academic'

@app.post("/api/users", response_model=schemas.User, status_code=status.HTTP_201_CREATED, tags=["Users"])
def register_user(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    if user_in.username:
        existing_username = db.query(models.User).filter(models.User.username == user_in.username).first()
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
            
    try:
        db_user = models.User(
            username=user_in.username,
            email=user_in.email,
            password_hash=hash_password(user_in.password),
            role=user_in.role,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            phone=user_in.phone,
            is_active=True
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to register user: {str(e)}"
        )

@app.post("/api/users/login", response_model=schemas.User, tags=["Users"])
def login_user(login_in: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == login_in.email).first()
    if not db_user or not verify_password(login_in.password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
    
    # Check source_app restrictions if provided
    if login_in.source_app:
        if login_in.source_app == "build":
            if db_user.role not in ["doctor", "patient", "admin"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account is not authorized to access the company website."
                )
        elif login_in.source_app == "academic":
            if db_user.role not in ["customer", "admin"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This account is not authorized to access the Academic website."
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source_app parameter."
            )
            
    return db_user

@app.get("/api/users", response_model=List[schemas.User], tags=["Users"])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.User).offset(skip).limit(limit).all()

@app.get("/api/users/{user_id}", response_model=schemas.User, tags=["Users"])
def get_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    return db_user

@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    db.delete(db_user)
    db.commit()
    return None


# ===================================================
#   Xzense Analysis API Endpoints
# ===================================================

@app.post("/api/users/{user_id}/analyses", response_model=schemas.XzenseAnalysis, status_code=status.HTTP_201_CREATED, tags=["Xzense Analyses"])
def create_analysis(user_id: int, analysis_in: schemas.XzenseAnalysisCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    try:
        db_analysis = models.XzenseAnalysis(
            user_id=user_id,
            title=analysis_in.title,
            measurement_type=analysis_in.measurement_type,
            file1_name=analysis_in.file1_name,
            file1_data=analysis_in.file1_data,
            file2_name=analysis_in.file2_name,
            file2_data=analysis_in.file2_data,
            selected_time_start=analysis_in.selected_time_start,
            selected_time_end=analysis_in.selected_time_end,
            avg_frequency1=analysis_in.avg_frequency1,
            avg_frequency2=analysis_in.avg_frequency2,
            delta_f=analysis_in.delta_f
        )
        db.add(db_analysis)
        db.commit()
        db.refresh(db_analysis)
        return db_analysis
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create analysis: {str(e)}"
        )

@app.get("/api/analyses", response_model=List[schemas.XzenseAnalysis], tags=["Xzense Analyses"])
def list_analyses(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.XzenseAnalysis).offset(skip).limit(limit).all()

@app.get("/api/users/{user_id}/analyses", response_model=List[schemas.XzenseAnalysis], tags=["Xzense Analyses"])
def list_user_analyses(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    return db.query(models.XzenseAnalysis).filter(models.XzenseAnalysis.user_id == user_id).all()

@app.get("/api/analyses/{analysis_id}", response_model=schemas.XzenseAnalysis, tags=["Xzense Analyses"])
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    db_analysis = db.query(models.XzenseAnalysis).filter(models.XzenseAnalysis.id == analysis_id).first()
    if not db_analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID {analysis_id} not found"
        )
    return db_analysis

@app.delete("/api/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Xzense Analyses"])
def delete_analysis(analysis_id: int, db: Session = Depends(get_db)):
    db_analysis = db.query(models.XzenseAnalysis).filter(models.XzenseAnalysis.id == analysis_id).first()
    if not db_analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID {analysis_id} not found"
        )
    db.delete(db_analysis)
    db.commit()
    return None


# ===================================================
#   Lab Registration API Endpoints
# ===================================================

class LabRegistrationStatusUpdate(BaseModel):
    status: str

@app.post("/api/users/{user_id}/registrations", response_model=schemas.LabRegistration, status_code=status.HTTP_201_CREATED, tags=["Lab Registrations"])
def create_registration(user_id: int, reg_in: schemas.LabRegistrationCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    try:
        db_reg = models.LabRegistration(
            user_id=user_id,
            course_id=reg_in.course_id,
            status=reg_in.status
        )
        db.add(db_reg)
        db.commit()
        db.refresh(db_reg)
        return db_reg
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to register course: {str(e)}"
        )

@app.get("/api/registrations", response_model=List[schemas.LabRegistration], tags=["Lab Registrations"])
def list_registrations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.LabRegistration).offset(skip).limit(limit).all()

@app.get("/api/users/{user_id}/registrations", response_model=List[schemas.LabRegistration], tags=["Lab Registrations"])
def list_user_registrations(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    return db.query(models.LabRegistration).filter(models.LabRegistration.user_id == user_id).all()

@app.patch("/api/registrations/{registration_id}/status", response_model=schemas.LabRegistration, tags=["Lab Registrations"])
def update_registration_status(registration_id: int, status_update: LabRegistrationStatusUpdate, db: Session = Depends(get_db)):
    db_reg = db.query(models.LabRegistration).filter(models.LabRegistration.id == registration_id).first()
    if not db_reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration with ID {registration_id} not found"
        )
    
    db_reg.status = status_update.status
    db.commit()
    db.refresh(db_reg)
    return db_reg

@app.delete("/api/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Lab Registrations"])
def delete_registration(registration_id: int, db: Session = Depends(get_db)):
    db_reg = db.query(models.LabRegistration).filter(models.LabRegistration.id == registration_id).first()
    if not db_reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration with ID {registration_id} not found"
        )
    db.delete(db_reg)
    db.commit()
    return None


