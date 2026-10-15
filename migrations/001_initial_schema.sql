-- ====================================================================
-- Migration: 001_initial_schema.sql
-- Description: Module A Schema Foundation for BRAHMO Clinical AI
--              Enforces 100% provenance and event-sourced regulatory events.
--              Zero static boolean banned flags.
-- ====================================================================

-- 1. Schema Migrations Ledger
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
);

-- 2. Ingestion Batches (System Provenance Root)
CREATE TABLE IF NOT EXISTS ingestion_batches (
    batch_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_version TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    ingested_at TEXT NOT NULL
);

-- 3. Canonical Drug Products Master
CREATE TABLE IF NOT EXISTS drug_products (
    product_id TEXT PRIMARY KEY,
    brand_name TEXT NOT NULL,
    brand_name_normalized TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    dose_form TEXT NOT NULL,
    strength_text TEXT NOT NULL,
    is_fdc INTEGER NOT NULL CHECK (is_fdc IN (0, 1)),
    ingredient_count INTEGER NOT NULL,
    has_brand_collision INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_drug_products_brand_norm ON drug_products(brand_name_normalized);
CREATE INDEX IF NOT EXISTS idx_drug_products_batch ON drug_products(load_batch_id);

-- 4. Decomposed Product Ingredients (Active Salts & Strengths)
CREATE TABLE IF NOT EXISTS product_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    ingredient_order INTEGER NOT NULL,
    ingredient_name TEXT NOT NULL,
    ingredient_name_normalized TEXT NOT NULL,
    strength_value REAL NOT NULL,
    strength_unit TEXT NOT NULL,
    decomposition_confidence REAL NOT NULL,
    decomposition_method TEXT NOT NULL,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES drug_products(product_id),
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_product_ingredients_pid ON product_ingredients(product_id);
CREATE INDEX IF NOT EXISTS idx_product_ingredients_name_norm ON product_ingredients(ingredient_name_normalized);
CREATE INDEX IF NOT EXISTS idx_product_ingredients_batch ON product_ingredients(load_batch_id);

-- 5. NLEM Reference Catalog (National List of Essential Medicines)
CREATE TABLE IF NOT EXISTS nlem_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_name TEXT NOT NULL,
    medicine_name_normalized TEXT NOT NULL,
    therapeutic_category TEXT,
    care_levels TEXT NOT NULL,
    nlem_edition TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_nlem_reference_name_norm ON nlem_reference(medicine_name_normalized);

-- 6. Jan Aushadhi Catalog (Public Generic Scheme Products)
CREATE TABLE IF NOT EXISTS jan_aushadhi_catalog (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generic_name TEXT NOT NULL,
    generic_name_normalized TEXT NOT NULL,
    strength_text TEXT NOT NULL,
    pack_text TEXT NOT NULL,
    mrp_inr REAL NOT NULL,
    catalog_version TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_jan_aushadhi_generic_norm ON jan_aushadhi_catalog(generic_name_normalized);

-- 7. Event-Sourced Regulatory Register (Gazette Notifications)
-- Binding Law 7: Zero static boolean banned flags. Status is strictly derived by effective date & supersession.
CREATE TABLE IF NOT EXISTS regulatory_events (
    event_id TEXT PRIMARY KEY,
    notification_id TEXT NOT NULL,
    date_published TEXT NOT NULL,
    effective_date TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('PROHIBITED', 'STAY_GRANTED', 'RESTRICTED', 'WITHDRAWN')),
    target_type TEXT NOT NULL CHECK (target_type IN ('FDC', 'INGREDIENT', 'PRODUCT')),
    target_description TEXT NOT NULL,
    normalized_salts_key TEXT NOT NULL,
    scope_constraint TEXT,
    supersedes_event_id TEXT,
    note TEXT,
    source TEXT NOT NULL,
    source_version TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id),
    FOREIGN KEY (supersedes_event_id) REFERENCES regulatory_events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_regulatory_events_salts_key ON regulatory_events(normalized_salts_key);
CREATE INDEX IF NOT EXISTS idx_regulatory_events_dates ON regulatory_events(effective_date, action);
CREATE INDEX IF NOT EXISTS idx_regulatory_events_notification ON regulatory_events(notification_id);

-- 8. Severe Drug-Drug Interactions (Seed List)
CREATE TABLE IF NOT EXISTS severe_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_a TEXT NOT NULL,
    ingredient_a_normalized TEXT NOT NULL,
    ingredient_b TEXT NOT NULL,
    ingredient_b_normalized TEXT NOT NULL,
    severity TEXT NOT NULL,
    clinical_note TEXT NOT NULL,
    source_tag TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_severe_interactions_pair ON severe_interactions(ingredient_a_normalized, ingredient_b_normalized);

-- 9. Pharmacy Stock Normalized Ledger
CREATE TABLE IF NOT EXISTS pharmacy_stock_normalized (
    stock_row_id INTEGER PRIMARY KEY,
    item_name_as_billed TEXT NOT NULL,
    cleaned_brand_token TEXT NOT NULL,
    extracted_form_hint TEXT,
    extracted_pack_token TEXT,
    qty_units INTEGER NOT NULL,
    mrp_inr REAL NOT NULL,
    batch_no TEXT NOT NULL,
    expiry_yyyy_mm TEXT NOT NULL,
    is_expired INTEGER NOT NULL CHECK (is_expired IN (0, 1)),
    resolved_product_id TEXT,
    mapping_status TEXT NOT NULL CHECK (mapping_status IN ('RESOLVED', 'QUEUED_AMBIGUOUS', 'QUEUED_UNMAPPED')),
    mapping_confidence REAL NOT NULL,
    mapping_method TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (resolved_product_id) REFERENCES drug_products(product_id),
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_resolved_pid ON pharmacy_stock_normalized(resolved_product_id);
CREATE INDEX IF NOT EXISTS idx_stock_mapping_status ON pharmacy_stock_normalized(mapping_status);

-- 10. Ambiguity Review Queue
-- Binding Law 6: Zero silent auto-resolutions. Every uncertain mapping lands here.
CREATE TABLE IF NOT EXISTS ambiguity_review_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN ('PHARMACY_STOCK', 'PRESCRIPTION_ITEM', 'MASTER_DATA_ANOMALY')),
    source_ref_id TEXT NOT NULL,
    raw_input_text TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    candidate_product_ids_json TEXT NOT NULL,
    proposed_resolution_note TEXT,
    confidence_score REAL NOT NULL,
    detection_method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL,
    load_batch_id TEXT NOT NULL,
    FOREIGN KEY (load_batch_id) REFERENCES ingestion_batches(batch_id)
);

CREATE INDEX IF NOT EXISTS idx_ambiguity_status ON ambiguity_review_queue(status);
CREATE INDEX IF NOT EXISTS idx_ambiguity_source_ref ON ambiguity_review_queue(source_type, source_ref_id);
