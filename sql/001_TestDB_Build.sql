

-- Create the databases and their schemas
CREATE DATABASE IF NOT EXISTS datathon_test;
CREATE SCHEMA IF NOT EXISTS datathon_test.courtLens;

USE DATABASE datathon_test;
USE SCHEMA datathon_test.courtLens;

CREATE TABLE IF NOT EXISTS Location (
    location_id     INT IDENTITY(1,1) NOT NULL,
    location_name   VARCHAR NOT NULL COMMENT 'Location name',
    CONSTRAINT pk_location PRIMARY KEY (location_id),
    CONSTRAINT uq_location_name UNIQUE (location_name)
)
COMMENT = 'The location of a case. May require expanding';

CREATE TABLE IF NOT EXISTS Court (
    court_id        INT IDENTITY(1,1) NOT NULL,
    court_name      VARCHAR NOT NULL COMMENT 'The name of this court',
    CONSTRAINT pk_court PRIMARY KEY (court_id),
    CONSTRAINT uq_court_name UNIQUE (court_name)
)
COMMENT = 'Type of court (Supreme, District, etc)';

CREATE TABLE IF NOT EXISTS Decision_Type (
    decision_type_id    INT IDENTITY(1,1) NOT NULL,
    decision_type       VARCHAR COMMENT 'The type of decision. Enumeration unknown',
    CONSTRAINT pk_decision_type PRIMARY KEY (decision_type_id),
    CONSTRAINT uq_decision_type UNIQUE (decision_type)
)
COMMENT = 'The class of judgement reached on a decision';

CREATE TABLE IF NOT EXISTS Judge (
    judge_id        INT IDENTITY(1,1) NOT NULL,
    judge_name      VARCHAR COMMENT 'The name of judge or presiding officer',
    CONSTRAINT pk_judge PRIMARY KEY (judge_id),
    CONSTRAINT uq_judge_name UNIQUE (judge_name)
)
COMMENT = 'Records the legal official presiding on a decision';

CREATE TABLE IF NOT EXISTS Counsel (
    counsel_id      INT IDENTITY(1,1) NOT NULL,
    counsel_name    VARCHAR COMMENT 'The counsel''s name',
    CONSTRAINT pk_counsel PRIMARY KEY (counsel_id),
    CONSTRAINT uq_counsel_name UNIQUE (counsel_name)
)
COMMENT = 'A legal representative serving one of the parties';

CREATE TABLE IF NOT EXISTS Party (
    party_id        INT IDENTITY(1,1) NOT NULL,
    party_name      VARCHAR COMMENT 'The name of this party',
    CONSTRAINT pk_party PRIMARY KEY (party_id)
)
COMMENT = 'One of the plaintiffs etc in the case';

CREATE TABLE IF NOT EXISTS Position (
    position_id     INT IDENTITY(1,1) NOT NULL,
    position_name   VARCHAR COMMENT 'What role this party is taking in the court',
    CONSTRAINT pk_position PRIMARY KEY (position_id),
    CONSTRAINT uq_position_name UNIQUE (position_name)
)
COMMENT = 'Whether a party is a defendant, accuser etc';

CREATE TABLE IF NOT EXISTS Cited_Authority (
    cited_authority_id  INT IDENTITY(1,1) NOT NULL,
    citation_text       VARCHAR COMMENT 'The citation text',
    CONSTRAINT pk_cited_authority PRIMARY KEY (cited_authority_id)
)
COMMENT = 'A previous case or authority cited in a decision';

CREATE TABLE IF NOT EXISTS Source_Document (
    source_document_id  INT IDENTITY(1,1) NOT NULL,
    uri                 VARCHAR COMMENT 'The location of the source file',
    file_hash           VARCHAR COMMENT 'Hash of the file contents, used to detect re-ingestion of the same file',
    ingested_at         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()::TIMESTAMP_NTZ COMMENT 'When the document was ingested',
    CONSTRAINT pk_source_document PRIMARY KEY (source_document_id),
    CONSTRAINT uq_source_document_file_hash UNIQUE (file_hash)
)
COMMENT = 'A court document ingested by the tool. Provides traceability and prevents duplicate ingestion';


/* ---------------------------------------------------------------------------
   Core entities
--------------------------------------------------------------------------- */

CREATE TABLE IF NOT EXISTS Court_Case (
    case_id                 INT IDENTITY(1,1) NOT NULL COMMENT 'Our internal reference',
    file_number             VARCHAR NOT NULL COMMENT 'The case reference number (external). Format currently unknown',
    minute_book_reference   VARCHAR COMMENT 'The minute book reference, where applicable',
    location_id             INT NOT NULL COMMENT 'The location this case is heard at',
    court_id                INT NOT NULL COMMENT 'The court this case is heard at',
    CONSTRAINT pk_court_case PRIMARY KEY (case_id),
    CONSTRAINT uq_court_case_file_number UNIQUE (court_id, file_number),
    CONSTRAINT fk_court_case_location FOREIGN KEY (location_id) REFERENCES Location (location_id),
    CONSTRAINT fk_court_case_court FOREIGN KEY (court_id) REFERENCES Court (court_id)
)
COMMENT = 'Parent entity for a case';

CREATE TABLE IF NOT EXISTS Decision (
    decision_id         INT IDENTITY(1,1) NOT NULL,
    case_id             INT NOT NULL COMMENT 'The case this decision was made against',
    decision_date       DATE COMMENT 'The date of the decision',
    decision_type_id    INT COMMENT 'The type of decision reached',
    source_document_id  INT NOT NULL COMMENT 'The document this decision was extracted from',
    neutral_citation    VARCHAR COMMENT 'The decision''s own neutral citation, e.g. [2024] NZHC 123',
    CONSTRAINT pk_decision PRIMARY KEY (decision_id),
    CONSTRAINT uq_decision_neutral_citation UNIQUE (neutral_citation),
    CONSTRAINT fk_decision_case FOREIGN KEY (case_id) REFERENCES Court_Case (case_id),
    CONSTRAINT fk_decision_decision_type FOREIGN KEY (decision_type_id) REFERENCES Decision_Type (decision_type_id),
    CONSTRAINT fk_decision_source_document FOREIGN KEY (source_document_id) REFERENCES Source_Document (source_document_id)
)
COMMENT = 'An individual decision within a case. Many to one with Court_Case';


/* ---------------------------------------------------------------------------
   Link tables
--------------------------------------------------------------------------- */

CREATE TABLE IF NOT EXISTS Decision_Judge (
    decision_judge_id   INT IDENTITY(1,1) NOT NULL,
    judge_id            INT NOT NULL,
    decision_id         INT NOT NULL,
    CONSTRAINT pk_decision_judge PRIMARY KEY (decision_judge_id),
    CONSTRAINT uq_decision_judge UNIQUE (decision_id, judge_id),
    CONSTRAINT fk_decision_judge_judge FOREIGN KEY (judge_id) REFERENCES Judge (judge_id),
    CONSTRAINT fk_decision_judge_decision FOREIGN KEY (decision_id) REFERENCES Decision (decision_id)
)
COMMENT = 'A many-to-many table between judges and decisions. Allows multi-judge panels';

CREATE TABLE IF NOT EXISTS Citation_Decision (
    citation_decision_id    INT IDENTITY(1,1) NOT NULL,
    cited_authority_id      INT NOT NULL,
    decision_id             INT NOT NULL,
    CONSTRAINT pk_citation_decision PRIMARY KEY (citation_decision_id),
    CONSTRAINT uq_citation_decision UNIQUE (cited_authority_id, decision_id),
    CONSTRAINT fk_citation_decision_cited_authority FOREIGN KEY (cited_authority_id) REFERENCES Cited_Authority (cited_authority_id),
    CONSTRAINT fk_citation_decision_decision FOREIGN KEY (decision_id) REFERENCES Decision (decision_id)
)
COMMENT = 'A many-to-many table between cited authorities and decisions';

CREATE TABLE IF NOT EXISTS Party_Case (
    party_case_id   INT IDENTITY(1,1) NOT NULL,
    party_id        INT NOT NULL,
    position_id     INT NOT NULL COMMENT 'The party''s position in this case',
    case_id         INT NOT NULL,
    CONSTRAINT pk_party_case PRIMARY KEY (party_case_id),
    CONSTRAINT uq_party_case UNIQUE (case_id, party_id),
    CONSTRAINT fk_party_case_party FOREIGN KEY (party_id) REFERENCES Party (party_id),
    CONSTRAINT fk_party_case_position FOREIGN KEY (position_id) REFERENCES Position (position_id),
    CONSTRAINT fk_party_case_case FOREIGN KEY (case_id) REFERENCES Court_Case (case_id)
)
COMMENT = 'A many-to-many table between party and case, recording the party''s position in the case';

CREATE TABLE IF NOT EXISTS Appearance (
    appearance_id   INT IDENTITY(1,1) NOT NULL,
    party_id        INT NOT NULL,
    counsel_id      INT COMMENT 'The counsel representing this party. Null if the party is self-represented',
    decision_id     INT NOT NULL COMMENT 'The decision this counsel is representing this party in',
    CONSTRAINT pk_appearance PRIMARY KEY (appearance_id),
    CONSTRAINT uq_appearance UNIQUE (decision_id, party_id, counsel_id),
    CONSTRAINT fk_appearance_party FOREIGN KEY (party_id) REFERENCES Party (party_id),
    CONSTRAINT fk_appearance_counsel FOREIGN KEY (counsel_id) REFERENCES Counsel (counsel_id),
    CONSTRAINT fk_appearance_decision FOREIGN KEY (decision_id) REFERENCES Decision (decision_id)
)
COMMENT = 'Records which counsel appeared for which party in a decision';


