-- =====================================================================
-- He thong quan ly dau gia truc tuyen (DGTT) - Luoc do CSDL PostgreSQL
-- 10 thuc the, chuan hoa 3NF (Cach A: bids khong luu session_id)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. users - Nguoi dung (4 vai tro)
-- ---------------------------------------------------------------------
CREATE TABLE users (
    user_id        serial       NOT NULL,
    role           varchar(20)  NOT NULL,
    username       varchar(50)  NOT NULL,
    email          varchar(100) NOT NULL,
    phone          varchar(15),
    full_name      varchar(100) NOT NULL,
    password_hash  varchar(255) NOT NULL,
    status         varchar(20)  NOT NULL DEFAULT 'ACTIVE',
    created_at     timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_users PRIMARY KEY (user_id),
    CONSTRAINT uq_users_username UNIQUE (username),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT ck_users_role CHECK (role IN ('ADMIN', 'STAFF', 'AUCTIONEER', 'BIDDER')),
    CONSTRAINT ck_users_status CHECK (status IN ('ACTIVE', 'LOCKED'))
);

-- ---------------------------------------------------------------------
-- 2. asset_owners - Nguoi co tai san (khong co tai khoan)
-- ---------------------------------------------------------------------
CREATE TABLE asset_owners (
    owner_id             serial       NOT NULL,
    owner_type           varchar(20)  NOT NULL,
    name                 varchar(200) NOT NULL,
    id_number            varchar(20)  NOT NULL,
    representative_name  varchar(100),
    phone                varchar(15),
    email                varchar(100),
    address              varchar(255),
    created_at           timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_asset_owners PRIMARY KEY (owner_id),
    CONSTRAINT uq_asset_owners_id_number UNIQUE (id_number),
    CONSTRAINT ck_asset_owners_type CHECK (owner_type IN ('INDIVIDUAL', 'ORGANIZATION'))
);

-- ---------------------------------------------------------------------
-- 3. assets - Tai san dau gia
-- ---------------------------------------------------------------------
CREATE TABLE assets (
    asset_id     serial       NOT NULL,
    asset_code   varchar(30)  NOT NULL,
    owner_id     integer      NOT NULL,
    name         varchar(200) NOT NULL,
    description  text,
    status       varchar(30)  NOT NULL DEFAULT 'UPCOMING',
    is_public    boolean      NOT NULL DEFAULT false,
    created_by   integer      NOT NULL,
    created_at   timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_assets PRIMARY KEY (asset_id),
    CONSTRAINT uq_assets_code UNIQUE (asset_code),
    CONSTRAINT ck_assets_status CHECK (status IN ('UPCOMING', 'IN_AUCTION', 'ENDED', 'SUSPENDED_CANCELLED'))
);

-- ---------------------------------------------------------------------
-- 4. auction_sessions - Phien dau gia (cau hinh va thong bao)
--    Ma hien thi: 'PDG-' || session_id; status DRAFT = chua cong khai
--    Nguoi tao, thoi diem cong khai: ghi trong activity_logs
-- ---------------------------------------------------------------------
CREATE TABLE auction_sessions (
    session_id             serial         NOT NULL,
    asset_id               integer        NOT NULL,
    auctioneer_id          integer        NOT NULL,
    starting_price         numeric(18,0)  NOT NULL,
    bid_increment          numeric(18,0)  NOT NULL,
    deposit_amount         numeric(18,0)  NOT NULL,
    registration_deadline  timestamp      NOT NULL,
    deposit_deadline       timestamp      NOT NULL,
    start_time             timestamp      NOT NULL,
    end_time               timestamp      NOT NULL,
    status                 varchar(30)    NOT NULL DEFAULT 'DRAFT',
    notice_content         text,
    CONSTRAINT pk_auction_sessions PRIMARY KEY (session_id),
    CONSTRAINT ck_sessions_starting_price CHECK (starting_price > 0),
    CONSTRAINT ck_sessions_bid_increment CHECK (bid_increment > 0),
    CONSTRAINT ck_sessions_deposit CHECK (deposit_amount >= 0),
    CONSTRAINT ck_sessions_registration_deadline CHECK (registration_deadline < start_time),
    CONSTRAINT ck_sessions_deposit_deadline CHECK (deposit_deadline < start_time),
    CONSTRAINT ck_sessions_time CHECK (start_time < end_time),
    CONSTRAINT ck_sessions_status CHECK (status IN ('DRAFT', 'OPEN_FOR_REGISTRATION', 'UPCOMING', 'IN_PROGRESS', 'PAUSED', 'ENDED', 'CANCELLED'))
);

-- ---------------------------------------------------------------------
-- 5. registrations - Ho so dang ky tham gia tung phien
-- ---------------------------------------------------------------------
CREATE TABLE registrations (
    registration_id      serial       NOT NULL,
    session_id           integer      NOT NULL,
    bidder_id            integer      NOT NULL,
    submitted_full_name  varchar(100) NOT NULL,
    submitted_id_number  varchar(20)  NOT NULL,
    submitted_address    varchar(255),
    submitted_phone      varchar(15),
    submission_count     integer      NOT NULL DEFAULT 1,
    status               varchar(30)  NOT NULL DEFAULT 'PENDING',
    supplement_deadline  timestamp,
    bidder_alias         varchar(20),
    submitted_at         timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_registrations PRIMARY KEY (registration_id),
    CONSTRAINT uq_registrations_session_bidder UNIQUE (session_id, bidder_id),
    CONSTRAINT uq_registrations_session_alias UNIQUE (session_id, bidder_alias),
    CONSTRAINT ck_registrations_status CHECK (status IN ('PENDING', 'NEEDS_SUPPLEMENT', 'APPROVED', 'REJECTED')),
    CONSTRAINT ck_registrations_submission_count CHECK (submission_count >= 1)
);

-- ---------------------------------------------------------------------
-- 6. registration_reviews - Lich su doi chieu va xet duyet ho so
-- ---------------------------------------------------------------------
CREATE TABLE registration_reviews (
    review_id        serial       NOT NULL,
    registration_id  integer      NOT NULL,
    review_type      varchar(30)  NOT NULL,
    result           varchar(10),
    reason           varchar(500),
    evidence         varchar(500),
    reviewed_by      integer      NOT NULL,
    reviewed_at      timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_registration_reviews PRIMARY KEY (review_id),
    CONSTRAINT ck_reviews_type CHECK (review_type IN ('DOCUMENT_CHECK', 'ELIGIBILITY_CHECK', 'DEPOSIT_CHECK', 'APPROVE', 'REQUEST_SUPPLEMENT', 'REJECT')),
    CONSTRAINT ck_reviews_result CHECK (result IN ('PASSED', 'FAILED'))
);

-- ---------------------------------------------------------------------
-- 7. bids - Luot tra gia (ghi ca lenh bi tu choi; khong sua/xoa)
-- ---------------------------------------------------------------------
CREATE TABLE bids (
    bid_id            serial         NOT NULL,
    transaction_code  varchar(50)    NOT NULL,
    registration_id   integer        NOT NULL,
    amount            numeric(18,0)  NOT NULL,
    result            varchar(10)    NOT NULL,
    rejection_reason  varchar(255),
    sequence_no       integer        NOT NULL,
    server_time       timestamp      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_bids PRIMARY KEY (bid_id),
    CONSTRAINT uq_bids_transaction_code UNIQUE (transaction_code),
    CONSTRAINT ck_bids_amount CHECK (amount > 0),
    CONSTRAINT ck_bids_result CHECK (result IN ('ACCEPTED', 'REJECTED'))
);

-- ---------------------------------------------------------------------
-- 8. auction_results - Ket qua dau gia (moi lan dieu chinh la 1 phien ban)
--    winning_bid_id rong = dau gia khong thanh cong
-- ---------------------------------------------------------------------
CREATE TABLE auction_results (
    result_id          serial       NOT NULL,
    session_id         integer      NOT NULL,
    version_no         integer      NOT NULL DEFAULT 1,
    winning_bid_id     integer,
    status             varchar(20)  NOT NULL DEFAULT 'DRAFT',
    exception_note     text,
    adjustment_reason  varchar(500),
    confirmed_by       integer,
    confirmed_at       timestamp,
    minutes_url        varchar(500),
    CONSTRAINT pk_auction_results PRIMARY KEY (result_id),
    CONSTRAINT uq_auction_results_session_version UNIQUE (session_id, version_no),
    CONSTRAINT ck_results_status CHECK (status IN ('DRAFT', 'CONFIRMED', 'SUPERSEDED')),
    CONSTRAINT ck_results_version CHECK (version_no >= 1)
);

-- ---------------------------------------------------------------------
-- 9. attachments - Tep dinh kem (anh/ho so tai san, giay to ho so)
-- ---------------------------------------------------------------------
CREATE TABLE attachments (
    attachment_id    serial       NOT NULL,
    asset_id         integer,
    registration_id  integer,
    submission_no    integer,
    file_type        varchar(30)  NOT NULL,
    file_name        varchar(255) NOT NULL,
    file_url         varchar(500) NOT NULL,
    file_format      varchar(10),
    file_size        bigint,
    display_order    integer,
    uploaded_at      timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_attachments PRIMARY KEY (attachment_id),
    CONSTRAINT ck_attachments_owner CHECK ((asset_id IS NOT NULL AND registration_id IS NULL) OR (asset_id IS NULL AND registration_id IS NOT NULL)),
    CONSTRAINT ck_attachments_type CHECK (file_type IN ('ASSET_IMAGE', 'ASSET_DOCUMENT', 'IDENTITY_DOCUMENT', 'DEPOSIT_RECEIPT', 'OTHER'))
);

-- ---------------------------------------------------------------------
-- 10. activity_logs - Nhat ky hoat dong (chi ghi them)
-- ---------------------------------------------------------------------
CREATE TABLE activity_logs (
    log_id       serial       NOT NULL,
    user_id      integer,
    action       varchar(50)  NOT NULL,
    entity_type  varchar(50)  NOT NULL,
    entity_id    integer,
    field_name   varchar(100),
    old_value    text,
    new_value    text,
    reason       varchar(500),
    created_at   timestamp    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_activity_logs PRIMARY KEY (log_id)
);

-- =====================================================================
-- Khoa ngoai
-- =====================================================================
ALTER TABLE assets
    ADD CONSTRAINT fk_assets_owner FOREIGN KEY (owner_id) REFERENCES asset_owners (owner_id);
ALTER TABLE assets
    ADD CONSTRAINT fk_assets_created_by FOREIGN KEY (created_by) REFERENCES users (user_id);

ALTER TABLE auction_sessions
    ADD CONSTRAINT fk_sessions_asset FOREIGN KEY (asset_id) REFERENCES assets (asset_id);
ALTER TABLE auction_sessions
    ADD CONSTRAINT fk_sessions_auctioneer FOREIGN KEY (auctioneer_id) REFERENCES users (user_id);

ALTER TABLE registrations
    ADD CONSTRAINT fk_registrations_session FOREIGN KEY (session_id) REFERENCES auction_sessions (session_id);
ALTER TABLE registrations
    ADD CONSTRAINT fk_registrations_bidder FOREIGN KEY (bidder_id) REFERENCES users (user_id);

ALTER TABLE registration_reviews
    ADD CONSTRAINT fk_reviews_registration FOREIGN KEY (registration_id) REFERENCES registrations (registration_id);
ALTER TABLE registration_reviews
    ADD CONSTRAINT fk_reviews_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES users (user_id);

ALTER TABLE bids
    ADD CONSTRAINT fk_bids_registration FOREIGN KEY (registration_id) REFERENCES registrations (registration_id);

ALTER TABLE auction_results
    ADD CONSTRAINT fk_results_session FOREIGN KEY (session_id) REFERENCES auction_sessions (session_id);
ALTER TABLE auction_results
    ADD CONSTRAINT fk_results_winning_bid FOREIGN KEY (winning_bid_id) REFERENCES bids (bid_id);
ALTER TABLE auction_results
    ADD CONSTRAINT fk_results_confirmed_by FOREIGN KEY (confirmed_by) REFERENCES users (user_id);

ALTER TABLE attachments
    ADD CONSTRAINT fk_attachments_asset FOREIGN KEY (asset_id) REFERENCES assets (asset_id);
ALTER TABLE attachments
    ADD CONSTRAINT fk_attachments_registration FOREIGN KEY (registration_id) REFERENCES registrations (registration_id);

ALTER TABLE activity_logs
    ADD CONSTRAINT fk_activity_logs_user FOREIGN KEY (user_id) REFERENCES users (user_id);

-- =====================================================================
-- Moi phien chi co toi da 1 ket qua da xac nhan
-- =====================================================================
CREATE UNIQUE INDEX uq_results_one_confirmed ON auction_results (session_id) WHERE status = 'CONFIRMED';

-- =====================================================================
-- Chu thich (hien thi trong DrawSQL)
-- =====================================================================
COMMENT ON TABLE users IS 'Nguoi dung he thong: quan tri vien, nhan vien, dau gia vien, nguoi tham gia';
COMMENT ON TABLE asset_owners IS 'Nguoi co tai san dau gia (khong co tai khoan)';
COMMENT ON TABLE assets IS 'Tai san dau gia';
COMMENT ON TABLE auction_sessions IS 'Phien dau gia: cau hinh va thong bao';
COMMENT ON TABLE auction_results IS 'Ket qua dau gia theo phien ban: du thao, da xac nhan, bi thay the';
COMMENT ON TABLE registrations IS 'Ho so dang ky tham gia tung phien';
COMMENT ON TABLE registration_reviews IS 'Lich su doi chieu va xet duyet ho so';
COMMENT ON TABLE bids IS 'Luot tra gia, gom ca lenh bi tu choi';
COMMENT ON TABLE attachments IS 'Tep dinh kem cua tai san hoac ho so';
COMMENT ON TABLE activity_logs IS 'Nhat ky hoat dong, chi ghi them';
