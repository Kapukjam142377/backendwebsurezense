from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import hashlib
import secrets
import os
import stripe
import jwt
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import models
import schemas
import database
from database import engine, get_db

load_dotenv()  # Loaded environment variables including FRONTEND_URL and database URL

# JWT Config
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "surezense_secret_key_change_in_production_2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Create all database tables on startup (if they do not exist yet)
models.Base.metadata.create_all(bind=engine)

# Auto-migrate table columns for existing databases
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token VARCHAR(255);"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token_expires TIMESTAMP;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token VARCHAR(255);"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires TIMESTAMP;"))
        conn.commit()
except Exception as migrate_err:
    print(f"[DB MIGRATION NOTICE] Auto-column migration note: {migrate_err}")

app = FastAPI(
    title="Surazense Cancer Report API",
    description="Backend API for Surazense Cancer Detection Diagnostic Reports",
    version="1.0.0"
)

# Configure Cross-Origin Resource Sharing (CORS)
# Allows the separate React frontend to securely request data from this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
        # Check if this Stripe session already has a recorded transaction (prevents duplicate orders on double-submit/refresh)
        if order_in.stripe_session_id:
            existing_tx = db.query(models.PaymentTransaction).filter(models.PaymentTransaction.transaction_ref == order_in.stripe_session_id).first()
            if existing_tx:
                existing_order = db.query(models.Order).filter(models.Order.id == existing_tx.order_id).first()
                if existing_order:
                    return existing_order

        # Calculate total price of all order items
        total_amount = sum(item.price * item.quantity for item in order_in.items)

        # Create Order Header
        db_order = models.Order(
            user_id=order_in.user_id,
            customer_name=order_in.customer_name,
            customer_email=order_in.customer_email,
            customer_phone=order_in.customer_phone,
            shipping_address=order_in.shipping_address,
            payment_method=order_in.payment_method,
            payment_status=order_in.payment_status or "pending",
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

        # Create Payment Transaction if stripe_session_id is provided
        if order_in.stripe_session_id:
            db_tx = models.PaymentTransaction(
                order_id=db_order.id,
                gateway="Stripe",
                transaction_ref=order_in.stripe_session_id,
                amount=total_amount,
                currency="THB",
                status="success" if order_in.payment_status == "paid" else "pending",
                payment_method="card"
            )
            db.add(db_tx)

        db.commit()
        db.refresh(db_order)
        return db_order
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to place order ({type(e).__name__}): {str(e)}"
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

# 6. Create Stripe Checkout Session
@app.post("/api/checkout/create-session", tags=["Stripe Checkout"])
def create_stripe_checkout_session(order_in: schemas.OrderCreate):
    try:
        stripe_key = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="STRIPE_SECRET_KEY is not configured on the server."
            )
        stripe.api_key = stripe_key

        line_items = []
        for item in order_in.items:
            line_items.append({
                "price_data": {
                    "currency": "thb",
                    "product_data": {
                        "name": item.product_name,
                    },
                    "unit_amount": int(round(item.price * 100)), # Amount in smallest currency unit (satang/cents)
                },
                "quantity": item.quantity,
            })

        domain_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            customer_email=order_in.customer_email,
            success_url=f"{domain_url}/checkout?status=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{domain_url}/checkout?status=cancel",
            metadata={
                "customer_name": order_in.customer_name,
                "customer_email": order_in.customer_email,
                "shipping_address": order_in.shipping_address,
            }
        )

        return {"checkout_url": session.url, "session_id": session.id}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create Stripe Checkout session: {str(e)}"
        )


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
#   User Management & Auth API Endpoints
# ===================================================

class UserLogin(BaseModel):
    email: str
    password: str

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
        verif_token = secrets.token_urlsafe(32)
        verif_expires = datetime.now() + timedelta(hours=24)
        
        db_user = models.User(
            username=user_in.username,
            email=user_in.email,
            password_hash=hash_password(user_in.password),
            role=user_in.role,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            phone=user_in.phone,
            is_active=True,
            is_verified=False,
            verification_token=verif_token,
            verification_token_expires=verif_expires
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        verif_link = f"{frontend_url}/verify-email?token={verif_token}"
        print(f"[AUTH DEV LOG] New Registration - Verification link for {user_in.email}: {verif_link}")
        
        return db_user
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to register user: {str(e)}"
        )

@app.post("/api/users/login", response_model=schemas.TokenResponse, tags=["Users"])
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
        
    access_token = create_access_token(data={"sub": str(db_user.id), "email": db_user.email, "role": db_user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user
    }

@app.post("/api/users/forgot-password", tags=["Users Password Reset"])
def forgot_password(req: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == req.email).first()
    if not db_user:
        return {"message": "If the email is registered, a password reset link has been sent."}
    
    reset_tok = secrets.token_urlsafe(32)
    db_user.reset_token = reset_tok
    db_user.reset_token_expires = datetime.now() + timedelta(hours=1)
    db.commit()
    
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    reset_link = f"{frontend_url}/reset-password?token={reset_tok}"
    print(f"[AUTH DEV LOG] Password reset link for {req.email}: {reset_link}")
    
    return {
        "message": "If the email is registered, a password reset link has been sent.",
        "reset_token": reset_tok
    }

@app.post("/api/users/verify-reset-token", tags=["Users Password Reset"])
def verify_reset_token(req: schemas.VerifyResetTokenRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.reset_token == req.token).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )
    if db_user.reset_token_expires and db_user.reset_token_expires < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    return {
        "valid": True,
        "email": db_user.email
    }

@app.post("/api/users/reset-password", tags=["Users Password Reset"])
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.reset_token == req.token).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )
    if db_user.reset_token_expires and db_user.reset_token_expires < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
    
    db_user.password_hash = hash_password(req.new_password)
    db_user.reset_token = None
    db_user.reset_token_expires = None
    db.commit()
    
    return {"message": "Password reset successfully. You may now log in with your new password."}

@app.post("/api/users/verify-email", tags=["Users Email Verification"])
def verify_email(req: schemas.VerifyEmailRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.verification_token == req.token).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token"
        )
    if db_user.verification_token_expires and db_user.verification_token_expires < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired"
        )
    
    db_user.is_verified = True
    db_user.verification_token = None
    db_user.verification_token_expires = None
    db.commit()
    
    return {"message": "Email verified successfully", "is_verified": True}

@app.post("/api/users/resend-verification", tags=["Users Email Verification"])
def resend_verification(req: schemas.ResendVerificationRequest, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == req.email).first()
    if not db_user:
        return {"message": "If the email is registered, a new verification link has been sent."}
    
    if db_user.is_verified:
        return {"message": "Email is already verified."}
        
    verif_tok = secrets.token_urlsafe(32)
    db_user.verification_token = verif_tok
    db_user.verification_token_expires = datetime.now() + timedelta(hours=24)
    db.commit()
    
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    verif_link = f"{frontend_url}/verify-email?token={verif_tok}"
    print(f"[AUTH DEV LOG] Email verification link for {req.email}: {verif_link}")
    
    return {
        "message": "If the email is registered, a new verification link has been sent.",
        "verification_token": verif_tok
    }

@app.get("/api/auth/{provider}", response_model=schemas.SocialAuthResponse, tags=["Social Auth"])
def get_social_auth_url(provider: str):
    provider_lower = provider.lower()
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    if provider_lower == "google":
        client_id = os.getenv("GOOGLE_CLIENT_ID", "mock-google-client-id")
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={frontend_url}/auth/google/callback&scope=openid%20email%20profile"
    elif provider_lower in ["facebook", "fb"]:
        client_id = os.getenv("FACEBOOK_CLIENT_ID", "mock-facebook-client-id")
        auth_url = f"https://www.facebook.com/v18.0/dialog/oauth?client_id={client_id}&redirect_uri={frontend_url}/auth/facebook/callback&scope=email,public_profile"
    elif provider_lower == "line":
        client_id = os.getenv("LINE_CHANNEL_ID", "mock-line-channel-id")
        auth_url = f"https://access.line.me/oauth2/v2.1/authorize?response_type=code&client_id={client_id}&redirect_uri={frontend_url}/auth/line/callback&state=surezense_state&scope=profile%20openid%20email"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Supported providers: google, facebook, line."
        )
        
    return {
        "provider": provider_lower,
        "auth_url": auth_url
    }

@app.get("/api/users", response_model=List[schemas.User], tags=["Users"])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.User).offset(skip).limit(limit).all()

class UserRoleUpdate(BaseModel):
    role: str

@app.patch("/api/users/{user_id}/role", response_model=schemas.User, tags=["Users"])
def update_user_role(user_id: int, role_update: UserRoleUpdate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    db_user.role = role_update.role
    db.commit()
    db.refresh(db_user)
    return db_user

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


# ===================================================
#   Competition Profile API Endpoints
# ===================================================

@app.post("/api/users/{user_id}/competition-profile", response_model=schemas.CompetitionProfile, status_code=status.HTTP_201_CREATED, tags=["Competition Profiles"])
def create_competition_profile(user_id: int, profile_in: schemas.CompetitionProfileCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Check if profile already exists
    existing_profile = db.query(models.CompetitionProfile).filter(models.CompetitionProfile.user_id == user_id).first()
    if existing_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with ID {user_id} already has a competition profile"
        )
    
    try:
        db_profile = models.CompetitionProfile(
            user_id=user_id,
            title_name=profile_in.title_name,
            custom_title_name=profile_in.custom_title_name,
            nickname=profile_in.nickname,
            middle_name=profile_in.middle_name,
            id_number=profile_in.id_number,
            mobile_number=profile_in.mobile_number,
            education=profile_in.education,
            institution_name=profile_in.institution_name,
            current_address=profile_in.current_address,
            institution_address=profile_in.institution_address,
            student_card_front=profile_in.student_card_front,
            student_card_back=profile_in.student_card_back
        )
        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)
        return db_profile
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create competition profile: {str(e)}"
        )

@app.get("/api/users/{user_id}/competition-profile", response_model=schemas.CompetitionProfile, tags=["Competition Profiles"])
def get_user_competition_profile(user_id: int, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    db_profile = db.query(models.CompetitionProfile).filter(models.CompetitionProfile.user_id == user_id).first()
    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competition profile not found for user ID {user_id}"
        )
    return db_profile

@app.get("/api/competition-profiles", response_model=List[schemas.CompetitionProfile], tags=["Competition Profiles"])
def list_competition_profiles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.CompetitionProfile).offset(skip).limit(limit).all()

@app.patch("/api/users/{user_id}/competition-profile", response_model=schemas.CompetitionProfile, tags=["Competition Profiles"])
def update_competition_profile(user_id: int, profile_update: schemas.CompetitionProfileUpdate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    db_profile = db.query(models.CompetitionProfile).filter(models.CompetitionProfile.user_id == user_id).first()
    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competition profile not found for user ID {user_id}"
        )
    
    try:
        # Update only fields provided in the body
        update_data = profile_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_profile, key, value)
        
        db.commit()
        db.refresh(db_profile)
        return db_profile
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update competition profile: {str(e)}"
        )

@app.delete("/api/users/{user_id}/competition-profile", status_code=status.HTTP_204_NO_CONTENT, tags=["Competition Profiles"])
def delete_competition_profile(user_id: int, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    db_profile = db.query(models.CompetitionProfile).filter(models.CompetitionProfile.user_id == user_id).first()
    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Competition profile not found for user ID {user_id}"
        )
    
    try:
        db.delete(db_profile)
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete competition profile: {str(e)}"
        )



