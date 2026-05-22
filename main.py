from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
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
    allow_origins=["*"],  # Adjust this in production to match your React app's domain (e.g. ['https://my-app.com'])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Surazense Cancer Report API is running successfully!",
        "docs_url": "/docs"  # Auto-generated Swagger documentation path
    }

# 1. Create a Full Report (creates patient, report, markers, and genetics in a single transaction)
@app.post("/api/reports", response_model=schemas.MedicalReport, status_code=status.HTTP_201_CREATED)
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
@app.get("/api/reports/{report_id}", response_model=schemas.MedicalReport)
def get_report(report_id: int, db: Session = Depends(get_db)):
    db_report = db.query(models.MedicalReport).filter(models.MedicalReport.id == report_id).first()
    if not db_report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    return db_report

# 3. List All Reports
@app.get("/api/reports", response_model=List[schemas.MedicalReport])
def list_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    reports = db.query(models.MedicalReport).offset(skip).limit(limit).all()
    return reports

# 4. Delete a Report (cascades delete to markers and genetics tables)
@app.delete("/api/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
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
@app.post("/api/orders", response_model=schemas.Order, status_code=status.HTTP_201_CREATED)
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
@app.get("/api/orders", response_model=List[schemas.Order])
def list_orders(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    orders = db.query(models.Order).offset(skip).limit(limit).all()
    return orders

# 3. Get Specific Order
@app.get("/api/orders/{order_id}", response_model=schemas.Order)
def get_order(order_id: int, db: Session = Depends(get_db)):
    db_order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    return db_order

# 4. Update Order / Payment Status
@app.patch("/api/orders/{order_id}/status", response_model=schemas.Order)
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
@app.delete("/api/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
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

