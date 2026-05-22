-- SQL Schema for Surazense Cancer Report Database (PostgreSQL Compatible)
-- This schema matches the SQLAlchemy models defined in the Python backend.

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'customer', -- 'patient', 'doctor', 'customer', 'admin'
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast user lookup by email
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);


-- 2. Patients Table
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    sex VARCHAR(50),
    age INTEGER,
    dob DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast patient lookup by name
CREATE INDEX IF NOT EXISTS idx_patients_name ON patients(name);


-- 3. Medical Reports Table (Linked to Patients)
CREATE TABLE IF NOT EXISTS medical_reports (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    doctor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    specimen1 VARCHAR(100),
    specimen2 VARCHAR(100),
    collecting_date DATE,
    receiving_date DATE,
    testing_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast report lookup by patient
CREATE INDEX IF NOT EXISTS idx_medical_reports_patient_id ON medical_reports(patient_id);


-- 4. Tumor Markers & Clinical Scores Table (One-to-One with Medical Reports)
CREATE TABLE IF NOT EXISTS tumor_markers (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL UNIQUE REFERENCES medical_reports(id) ON DELETE CASCADE,
    psa NUMERIC(10, 2),
    cea NUMERIC(10, 2),
    ca153 NUMERIC(10, 2),
    afp NUMERIC(10, 2),
    hpv VARCHAR(100),
    ctcs NUMERIC(10, 2),
    pca3 NUMERIC(10, 2),
    dlx1 VARCHAR(100)
);


-- 5. Genetic Mutations / Exons Table (One-to-One with Medical Reports)
CREATE TABLE IF NOT EXISTS genetic_mutations (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL UNIQUE REFERENCES medical_reports(id) ON DELETE CASCADE,
    exon20 NUMERIC(10, 2),
    g719x NUMERIC(10, 2),
    exon19 NUMERIC(10, 2),
    l858r NUMERIC(10, 2)
);


-- 6. Products Table
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    sku VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    image_url VARCHAR(500),
    stock_quantity INTEGER DEFAULT 0,
    category VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast product lookup by SKU
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);


-- 7. Orders Table
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(50),
    shipping_address VARCHAR(1000) NOT NULL,
    payment_method VARCHAR(100) NOT NULL,
    payment_status VARCHAR(50) DEFAULT 'pending',
    order_status VARCHAR(50) DEFAULT 'received',
    total_amount NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast order lookup by customer email
CREATE INDEX IF NOT EXISTS idx_orders_customer_email ON orders(customer_email);


-- 8. Order Items Table
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name VARCHAR(255) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    quantity INTEGER NOT NULL
);

-- Index for fast item lookup by order_id
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);


-- 9. Payment Transactions Table
CREATE TABLE IF NOT EXISTS payment_transactions (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    gateway VARCHAR(50) NOT NULL, -- e.g. 'OPN', '2C2P', 'WooCommerce'
    transaction_ref VARCHAR(255) UNIQUE NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(10) DEFAULT 'THB',
    status VARCHAR(50) NOT NULL, -- e.g. 'success', 'pending', 'failed', 'refunded'
    payment_method VARCHAR(50),
    raw_response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- 10. Xzense Analyses Table (Online Software Analysis History)
CREATE TABLE IF NOT EXISTS xzense_analyses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    measurement_type VARCHAR(20) NOT NULL, -- 'single' or 'dual'
    file1_name VARCHAR(255) NOT NULL,
    file1_data TEXT NOT NULL, -- Stored as JSON string
    file2_name VARCHAR(255),
    file2_data TEXT, -- Stored as JSON string (nullable for single measurement)
    selected_time_start NUMERIC(12, 4),
    selected_time_end NUMERIC(12, 4),
    avg_frequency1 NUMERIC(15, 4),
    avg_frequency2 NUMERIC(15, 4),
    delta_f NUMERIC(15, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast lookup of analyses by user_id
CREATE INDEX IF NOT EXISTS idx_xzense_analyses_user ON xzense_analyses(user_id);


-- 11. Lab Registrations Table
CREATE TABLE IF NOT EXISTS lab_registrations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'confirmed', 'completed', 'cancelled'
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
