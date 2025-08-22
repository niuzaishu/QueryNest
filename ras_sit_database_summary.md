# MongoDB Instance 'ras_sit' Database Summary

This document provides a detailed analysis of all databases found in the MongoDB instance 'ras_sit'.

## Overview

The 'ras_sit' MongoDB instance contains 2 databases:

1. **za_bank_ras** - Main database with 80 collections and approximately 45.8 million documents
2. **za_bank_ras_offlinetag** - Secondary database with 20 collections and 442 documents

## Database Details

### 1. za_bank_ras

This appears to be the main operational database for the banking risk assessment system.

**Statistics:**
- **Collections:** 80
- **Documents:** 45,800,688
- **Data Size:** 13.7 GB
- **Storage Size:** 3.19 GB
- **Index Size:** 2.9 GB

**Key Collections by Document Count:**
1. `offLineTagDetailMongoDo` - 41,038,453 documents (89.6% of total) - Appears to store tag/variable details
2. `dataCollectBinlogFailRecord` - 1,549,093 documents (3.4% of total) - Stores failed data collection records
3. `accuity_aml_list` - 2,695,481 documents (5.9% of total) - Likely contains AML watchlist data
4. `ciNoAndActNoMapping` - 377,884 documents - Maps customer IDs to account numbers
5. `scn_rule_decision_record` - 84,742 documents - Stores rule decision records for scenarios

**Key Collections by Purpose:**

1. **AML (Anti-Money Laundering) Related Collections:**
   - `amlStrFormData` - Suspicious transaction reports
   - `accuity_list_monitor_record` - Records of watchlist monitoring
   - `aml_grey_list` - Grey list for AML purposes
   - `amlStrExportRecord` - Records of exported STR reports
   - `aml_trans_black_list` - Black list for transaction monitoring
   - `amlScreenHitRecord` - Records of AML screening hits
   - `amlStrCaseProcess` - STR case processing workflow
   - `amlScreenResultCompare` - AML screening result comparison

2. **Fraud Detection Related Collections:**
   - `fraudCaseProcess` - Fraud case processing workflow
   - `fraudCaseDetail` - Detailed fraud case information
   - `antifraudRuleBuilder` - Fraud detection rules
   - `fc_data_record` - Financial crime data records
   - `fc_screening_record` - Financial crime screening records

3. **Operations Related Collections:**
   - `opsOperateLog` - Operation logs
   - `ops_dv_greylist` - Operations grey list
   - `ops_dv_blacklist` - Operations black list
   - `ops_card_list` - Card lists for operations

4. **Data Collection and Management:**
   - `dataCollectFieldMapping` - Field mappings for data collection
   - `dataCollectBinlogFailRecord` - Failed binary log records
   - `dataCollectTableMapping` - Table mappings for data collection
   - `table_info` - Database table information

5. **Offline Tags and Machine Learning:**
   - `offLineTagDetailMongoDo` - Offline tag details
   - `offlineNameList` - Offline name lists
   - `offlineNameListDTO` - DTO for offline name lists
   - `machineLearningRecord` - Machine learning model records

### 2. za_bank_ras_offlinetag

This database appears to be focused on storing offline tags and variables for various entities, likely used for analytics, risk assessment, or machine learning purposes.

**Statistics:**
- **Collections:** 20
- **Documents:** 442
- **Data Size:** 74.6 KB
- **Storage Size:** 0.5 MB
- **Index Size:** 860.0 KB

**Collection Patterns:**

The collections follow a naming pattern that indicates:
1. Entity type (e.g., `card_no`, `customer_no`, `user_id`)
2. Date stamp (e.g., `20250303`, `20250818`)

For example:
- `offlinetag_card_no_20250303`
- `offlinetag_customer_no_20250818`
- `offlinetag_user_id_20250804`

Most collections have fields starting with `o_`, suggesting these are offline variables or features calculated for different entities.

## Key Insights

1. **System Purpose**: The database structure indicates this is a comprehensive risk assessment system for a bank (likely "ZA Bank"), with strong focus on AML (Anti-Money Laundering) and fraud detection.

2. **Data Volume Distribution**: The data is highly concentrated in a few large collections:
   - 89.6% of documents are in the `offLineTagDetailMongoDo` collection
   - 5.9% in `accuity_aml_list`
   - 3.4% in `dataCollectBinlogFailRecord`

3. **Feature Engineering**: The `offlinetag` database suggests sophisticated feature engineering for risk models, with variables calculated for different entity types (cards, customers, users).

4. **Date-Based Data Organization**: Many collections in the `offlinetag` database include dates in their names, suggesting regular batch processing of variables.

5. **Risk Models**: Collections like `offlinetag_rlnRateSensitiveModel_20240728` indicate specialized risk models for different purposes.

## Usage Recommendations

1. For general querying of customer data, focus on the `za_bank_ras` database.

2. For AML and compliance related queries, explore the numerous AML-related collections.

3. For risk scoring and analytics, the `za_bank_ras_offlinetag` database contains pre-calculated variables and features.

4. Be cautious when querying large collections like `offLineTagDetailMongoDo` (41M+ documents) as it could impact performance.

5. For historical analysis, note the date-based collections in the `offlinetag` database, which can be used for time-based comparisons.

6. Use the detailed field information collected to understand the data structure before performing complex queries.