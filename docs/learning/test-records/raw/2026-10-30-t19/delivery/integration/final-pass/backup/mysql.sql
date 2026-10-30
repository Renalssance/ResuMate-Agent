-- MySQL dump 10.13  Distrib 8.4.13, for Linux (aarch64)
--
-- Host: localhost    Database: resumate
-- ------------------------------------------------------
-- Server version	8.4.13

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `agent_actions`
--

DROP TABLE IF EXISTS `agent_actions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `agent_actions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `run_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `interrupt_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `kind` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `status` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `response` json DEFAULT NULL,
  `answered_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_agent_action_interrupt` (`run_id`,`interrupt_id`),
  CONSTRAINT `agent_actions_ibfk_1` FOREIGN KEY (`run_id`) REFERENCES `agent_runs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `action_kind` CHECK ((`kind` in (_utf8mb4'input',_utf8mb4'approval'))),
  CONSTRAINT `action_status` CHECK ((`status` in (_utf8mb4'pending',_utf8mb4'answered')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `agent_actions`
--

LOCK TABLES `agent_actions` WRITE;
/*!40000 ALTER TABLE `agent_actions` DISABLE KEYS */;
INSERT INTO `agent_actions` VALUES ('50516fa5-dfa9-4f2e-85c8-ca8d35fa9627','c0ff09db-ac6c-4bf2-80f3-ad8862845f2a','8141cc4c65eff3cd8bec82468c21178b','input','{\"kind\": \"input\", \"question\": \"你负责什么工作？\"}','pending',NULL,NULL);
/*!40000 ALTER TABLE `agent_actions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `agent_run_events`
--

DROP TABLE IF EXISTS `agent_run_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `agent_run_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `run_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `seq` int NOT NULL,
  `type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_agent_run_event_seq` (`run_id`,`seq`),
  CONSTRAINT `agent_run_events_ibfk_1` FOREIGN KEY (`run_id`) REFERENCES `agent_runs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_agent_run_event_seq` CHECK ((`seq` > 0))
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `agent_run_events`
--

LOCK TABLES `agent_run_events` WRITE;
/*!40000 ALTER TABLE `agent_run_events` DISABLE KEYS */;
INSERT INTO `agent_run_events` VALUES (1,'b045bf75-e2f2-4bb8-8683-f043a1aecb56',1,'run.status','{\"status\": \"queued\", \"error_code\": null}','2026-10-30 03:34:39'),(2,'b045bf75-e2f2-4bb8-8683-f043a1aecb56',2,'run.status','{\"status\": \"running\", \"error_code\": null}','2026-10-30 03:34:39'),(3,'b045bf75-e2f2-4bb8-8683-f043a1aecb56',3,'artifact.created','{\"kind\": \"resume_pdf\", \"artifact_id\": \"b045bf75-e2f2-4bb8-8683-f043a1aecb56\"}','2026-10-30 03:34:40'),(4,'b045bf75-e2f2-4bb8-8683-f043a1aecb56',4,'run.status','{\"status\": \"succeeded\", \"error_code\": null}','2026-10-30 03:34:40'),(5,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',1,'run.status','{\"status\": \"queued\", \"error_code\": null}','2026-10-30 03:34:40'),(6,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',2,'run.status','{\"status\": \"running\", \"error_code\": null}','2026-10-30 03:34:40'),(7,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',3,'tool.started','{\"tool_name\": \"get_application_context\", \"operation_key\": \"call-0\"}','2026-10-30 03:34:40'),(8,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',4,'tool.completed','{\"tool_name\": \"get_application_context\", \"result_ref\": null, \"operation_key\": \"call-0\"}','2026-10-30 03:34:40'),(9,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',5,'tool.started','{\"tool_name\": \"ask_applicant\", \"operation_key\": \"call-1\"}','2026-10-30 03:34:40'),(10,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',6,'action.required','{\"kind\": \"input\", \"action_id\": \"50516fa5-dfa9-4f2e-85c8-ca8d35fa9627\"}','2026-10-30 03:34:40'),(11,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',7,'run.status','{\"status\": \"waiting_input\", \"error_code\": null}','2026-10-30 03:34:40');
/*!40000 ALTER TABLE `agent_run_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `agent_runs`
--

DROP TABLE IF EXISTS `agent_runs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `agent_runs` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `session_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `kind` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `input_json` json NOT NULL,
  `input_versions` json NOT NULL,
  `result_json` json DEFAULT NULL,
  `attempt` int NOT NULL,
  `execution_epoch` int NOT NULL,
  `heartbeat_at` datetime DEFAULT NULL,
  `cancel_requested_at` datetime DEFAULT NULL,
  `error_code` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `output_refs` json NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_agent_run_request` (`user_id`,`request_id`),
  KEY `session_id` (`session_id`,`user_id`),
  KEY `ix_agent_runs_status` (`status`),
  KEY `ix_agent_runs_user_id` (`user_id`),
  KEY `ix_agent_runs_session_id` (`session_id`),
  CONSTRAINT `agent_runs_ibfk_1` FOREIGN KEY (`session_id`, `user_id`) REFERENCES `agent_sessions` (`id`, `user_id`) ON DELETE CASCADE,
  CONSTRAINT `ck_agent_run_attempt` CHECK (((`attempt` >= 1) and (`execution_epoch` >= 0))),
  CONSTRAINT `run_status` CHECK ((`status` in (_utf8mb4'queued',_utf8mb4'running',_utf8mb4'waiting_input',_utf8mb4'waiting_approval',_utf8mb4'succeeded',_utf8mb4'failed',_utf8mb4'cancelled')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `agent_runs`
--

LOCK TABLES `agent_runs` WRITE;
/*!40000 ALTER TABLE `agent_runs` DISABLE KEYS */;
INSERT INTO `agent_runs` VALUES ('b045bf75-e2f2-4bb8-8683-f043a1aecb56',1,'c24c776a-2573-4ce7-abf9-358e45d4e462','delivery-pdf','resume_export','succeeded','{\"resumeVersionId\": \"delivery-confirmed\"}','{\"resumeVersion\": 3}',NULL,1,1,'2026-10-30 03:34:40',NULL,NULL,'[{\"id\": \"b045bf75-e2f2-4bb8-8683-f043a1aecb56\", \"type\": \"resume_pdf\", \"revision\": 3, \"resumeVersionId\": \"delivery-confirmed\"}]','2026-10-30 03:34:39','2026-10-30 03:34:40'),('c0ff09db-ac6c-4bf2-80f3-ad8862845f2a',1,'5f27d6ee-198a-4569-85cf-787712c2bf37','backup-waiting','tailoring','waiting_input','{\"jdId\": 1, \"resumeId\": 1, \"contextSnapshot\": {\"job\": {\"id\": 1, \"text\": \"Build APIs\", \"title\": \"Engineer\", \"structured\": {}, \"inputVersion\": \"2026-10-30T03:34:17\"}, \"facts\": [], \"match\": null, \"resume\": {\"id\": 1, \"text\": \"Synthetic original resume: API development\", \"structured\": {\"self_summary\": \"API development\"}, \"inputVersion\": \"2026-10-30T03:34:17\"}}}','{\"jd\": \"2026-10-30T03:34:17\", \"facts\": [], \"resume\": \"2026-10-30T03:34:17\", \"memories\": []}',NULL,1,1,'2026-10-30 03:34:40',NULL,NULL,'[]','2026-10-30 03:34:40','2026-10-30 03:34:40');
/*!40000 ALTER TABLE `agent_runs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `agent_sessions`
--

DROP TABLE IF EXISTS `agent_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `agent_sessions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `purpose` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `context_invalidated_at` datetime DEFAULT NULL,
  `checkpoint_deleted_at` datetime DEFAULT NULL,
  `active_run_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_agent_session_owner` (`id`,`user_id`),
  KEY `ix_agent_sessions_user_id` (`user_id`),
  CONSTRAINT `agent_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `agent_sessions`
--

LOCK TABLES `agent_sessions` WRITE;
/*!40000 ALTER TABLE `agent_sessions` DISABLE KEYS */;
INSERT INTO `agent_sessions` VALUES ('5f27d6ee-198a-4569-85cf-787712c2bf37',1,'tailoring',NULL,NULL,'c0ff09db-ac6c-4bf2-80f3-ad8862845f2a','2026-10-30 03:34:40'),('c24c776a-2573-4ce7-abf9-358e45d4e462',1,'resume_export',NULL,NULL,NULL,'2026-10-30 03:34:39');
/*!40000 ALTER TABLE `agent_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `analysis_candidates`
--

DROP TABLE IF EXISTS `analysis_candidates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `analysis_candidates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `resume_id` int NOT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `note` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_analysis_job_resume` (`job_id`,`resume_id`),
  KEY `ix_analysis_candidates_job_id` (`job_id`),
  KEY `ix_analysis_candidates_resume_id` (`resume_id`),
  KEY `ix_analysis_candidates_status` (`status`),
  CONSTRAINT `analysis_candidates_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `analysis_candidates_ibfk_2` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `analysis_candidates`
--

LOCK TABLES `analysis_candidates` WRITE;
/*!40000 ALTER TABLE `analysis_candidates` DISABLE KEYS */;
/*!40000 ALTER TABLE `analysis_candidates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `analysis_jobs`
--

DROP TABLE IF EXISTS `analysis_jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `analysis_jobs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `jd_id` int DEFAULT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `summary` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `config_json` json NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_analysis_jobs_status` (`status`),
  KEY `ix_analysis_jobs_user_id` (`user_id`),
  KEY `ix_analysis_jobs_jd_id` (`jd_id`),
  CONSTRAINT `analysis_jobs_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `analysis_jobs_ibfk_2` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `analysis_jobs`
--

LOCK TABLES `analysis_jobs` WRITE;
/*!40000 ALTER TABLE `analysis_jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `analysis_jobs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `business_memories`
--

DROP TABLE IF EXISTS `business_memories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `business_memories` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `kind` varchar(18) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `source_ref` json NOT NULL,
  `confirmed_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_business_memories_user_id` (`user_id`),
  CONSTRAINT `business_memories_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `business_memory_kind` CHECK ((`kind` in (_utf8mb4'preference',_utf8mb4'interview_feedback')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `business_memories`
--

LOCK TABLES `business_memories` WRITE;
/*!40000 ALTER TABLE `business_memories` DISABLE KEYS */;
/*!40000 ALTER TABLE `business_memories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chat_messages`
--

DROP TABLE IF EXISTS `chat_messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_messages` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_ref_id` int NOT NULL,
  `message_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `timestamp` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_chat_messages_id` (`id`),
  KEY `ix_chat_messages_session_ref_id` (`session_ref_id`),
  CONSTRAINT `chat_messages_ibfk_1` FOREIGN KEY (`session_ref_id`) REFERENCES `chat_sessions` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chat_messages`
--

LOCK TABLES `chat_messages` WRITE;
/*!40000 ALTER TABLE `chat_messages` DISABLE KEYS */;
/*!40000 ALTER TABLE `chat_messages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chat_sessions`
--

DROP TABLE IF EXISTS `chat_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chat_sessions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `session_id` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `metadata_json` json NOT NULL,
  `updated_at` datetime NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_session` (`user_id`,`session_id`),
  KEY `ix_chat_sessions_id` (`id`),
  KEY `ix_chat_sessions_session_id` (`session_id`),
  KEY `ix_chat_sessions_user_id` (`user_id`),
  CONSTRAINT `chat_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chat_sessions`
--

LOCK TABLES `chat_sessions` WRITE;
/*!40000 ALTER TABLE `chat_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `chat_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `follow_up_question_sets`
--

DROP TABLE IF EXISTS `follow_up_question_sets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `follow_up_question_sets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `candidate_id` int NOT NULL,
  `resume_id` int NOT NULL,
  `jd_id` int DEFAULT NULL,
  `questions` json NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_followup_job_candidate` (`job_id`,`candidate_id`),
  KEY `ix_follow_up_question_sets_job_id` (`job_id`),
  KEY `ix_follow_up_question_sets_jd_id` (`jd_id`),
  KEY `ix_follow_up_question_sets_resume_id` (`resume_id`),
  KEY `ix_follow_up_question_sets_candidate_id` (`candidate_id`),
  CONSTRAINT `follow_up_question_sets_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `follow_up_question_sets_ibfk_2` FOREIGN KEY (`candidate_id`) REFERENCES `analysis_candidates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `follow_up_question_sets_ibfk_3` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `follow_up_question_sets_ibfk_4` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `follow_up_question_sets`
--

LOCK TABLES `follow_up_question_sets` WRITE;
/*!40000 ALTER TABLE `follow_up_question_sets` DISABLE KEYS */;
/*!40000 ALTER TABLE `follow_up_question_sets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `interview_commands`
--

DROP TABLE IF EXISTS `interview_commands`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interview_commands` (
  `id` int NOT NULL AUTO_INCREMENT,
  `interview_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `client_message_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `request_json` json DEFAULT NULL,
  `ack_json` json DEFAULT NULL,
  `result_ref` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `status` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_command` (`interview_id`,`client_message_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `interview_commands_ibfk_1` FOREIGN KEY (`interview_id`) REFERENCES `interview_sessions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `interview_commands_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `interview_command_status` CHECK ((`status` in (_utf8mb4'accepted',_utf8mb4'succeeded',_utf8mb4'failed')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `interview_commands`
--

LOCK TABLES `interview_commands` WRITE;
/*!40000 ALTER TABLE `interview_commands` DISABLE KEYS */;
/*!40000 ALTER TABLE `interview_commands` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `interview_events`
--

DROP TABLE IF EXISTS `interview_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interview_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `interview_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `seq` int NOT NULL,
  `type` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `payload` json NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_event_seq` (`interview_id`,`seq`),
  CONSTRAINT `interview_events_ibfk_1` FOREIGN KEY (`interview_id`) REFERENCES `interview_sessions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_interview_event_seq` CHECK ((`seq` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `interview_events`
--

LOCK TABLES `interview_events` WRITE;
/*!40000 ALTER TABLE `interview_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `interview_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `interview_question_sets`
--

DROP TABLE IF EXISTS `interview_question_sets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interview_question_sets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `candidate_id` int NOT NULL,
  `resume_id` int NOT NULL,
  `jd_id` int DEFAULT NULL,
  `questions` json NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_question_job_candidate` (`job_id`,`candidate_id`),
  KEY `ix_interview_question_sets_job_id` (`job_id`),
  KEY `ix_interview_question_sets_candidate_id` (`candidate_id`),
  KEY `ix_interview_question_sets_jd_id` (`jd_id`),
  KEY `ix_interview_question_sets_resume_id` (`resume_id`),
  CONSTRAINT `interview_question_sets_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `interview_question_sets_ibfk_2` FOREIGN KEY (`candidate_id`) REFERENCES `analysis_candidates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `interview_question_sets_ibfk_3` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `interview_question_sets_ibfk_4` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `interview_question_sets`
--

LOCK TABLES `interview_question_sets` WRITE;
/*!40000 ALTER TABLE `interview_question_sets` DISABLE KEYS */;
/*!40000 ALTER TABLE `interview_question_sets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `interview_sessions`
--

DROP TABLE IF EXISTS `interview_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interview_sessions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `agent_session_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_snapshot` json DEFAULT NULL,
  `application_id` int DEFAULT NULL,
  `jd_id` int DEFAULT NULL,
  `resume_version_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `application_id` (`application_id`),
  KEY `jd_id` (`jd_id`),
  KEY `resume_version_id` (`resume_version_id`),
  KEY `ix_interview_sessions_user_id` (`user_id`),
  KEY `ix_interview_sessions_agent_session_id` (`agent_session_id`),
  CONSTRAINT `interview_sessions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `interview_sessions_ibfk_2` FOREIGN KEY (`agent_session_id`) REFERENCES `agent_sessions` (`id`),
  CONSTRAINT `interview_sessions_ibfk_3` FOREIGN KEY (`application_id`) REFERENCES `job_applications` (`id`) ON DELETE SET NULL,
  CONSTRAINT `interview_sessions_ibfk_4` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `interview_sessions_ibfk_5` FOREIGN KEY (`resume_version_id`) REFERENCES `resume_versions` (`id`),
  CONSTRAINT `interview_status` CHECK ((`status` in (_utf8mb4'active',_utf8mb4'finished')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `interview_sessions`
--

LOCK TABLES `interview_sessions` WRITE;
/*!40000 ALTER TABLE `interview_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `interview_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `interview_turns`
--

DROP TABLE IF EXISTS `interview_turns`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `interview_turns` (
  `id` int NOT NULL AUTO_INCREMENT,
  `interview_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `turn_index` int NOT NULL,
  `question` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_context` json DEFAULT NULL,
  `answer` longtext COLLATE utf8mb4_unicode_ci,
  `feedback` json DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_interview_turn` (`interview_id`,`turn_index`),
  CONSTRAINT `interview_turns_ibfk_1` FOREIGN KEY (`interview_id`) REFERENCES `interview_sessions` (`id`) ON DELETE CASCADE,
  CONSTRAINT `ck_interview_turn_index` CHECK ((`turn_index` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `interview_turns`
--

LOCK TABLES `interview_turns` WRITE;
/*!40000 ALTER TABLE `interview_turns` DISABLE KEYS */;
/*!40000 ALTER TABLE `interview_turns` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_application_schedules`
--

DROP TABLE IF EXISTS `job_application_schedules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_application_schedules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `application_id` int NOT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `starts_at` datetime NOT NULL,
  `ends_at` datetime NOT NULL,
  `note` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `completed_event_id` int DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_job_application_schedules_ends_at` (`ends_at`),
  KEY `ix_job_application_schedules_status` (`status`),
  KEY `ix_job_application_schedules_application_id` (`application_id`),
  KEY `ix_job_application_schedules_completed_event_id` (`completed_event_id`),
  KEY `ix_job_application_schedules_starts_at` (`starts_at`),
  CONSTRAINT `job_application_schedules_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `job_applications` (`id`) ON DELETE CASCADE,
  CONSTRAINT `job_application_schedules_ibfk_2` FOREIGN KEY (`completed_event_id`) REFERENCES `job_application_status_events` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_application_schedules`
--

LOCK TABLES `job_application_schedules` WRITE;
/*!40000 ALTER TABLE `job_application_schedules` DISABLE KEYS */;
/*!40000 ALTER TABLE `job_application_schedules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_application_status_events`
--

DROP TABLE IF EXISTS `job_application_status_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_application_status_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `application_id` int NOT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_at` datetime NOT NULL,
  `note` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_job_application_status_events_changed_at` (`changed_at`),
  KEY `ix_job_application_status_events_status` (`status`),
  KEY `ix_job_application_status_events_application_id` (`application_id`),
  CONSTRAINT `job_application_status_events_ibfk_1` FOREIGN KEY (`application_id`) REFERENCES `job_applications` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_application_status_events`
--

LOCK TABLES `job_application_status_events` WRITE;
/*!40000 ALTER TABLE `job_application_status_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `job_application_status_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_applications`
--

DROP TABLE IF EXISTS `job_applications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_applications` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `resume_id` int DEFAULT NULL,
  `jd_id` int DEFAULT NULL,
  `resume_version_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `submitted_snapshot` json DEFAULT NULL,
  `company` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `position` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `applied_date` date NOT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `job_url` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `source` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `notes` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_job_applications_applied_date` (`applied_date`),
  KEY `ix_job_applications_jd_id` (`jd_id`),
  KEY `ix_job_applications_resume_id` (`resume_id`),
  KEY `ix_job_applications_status` (`status`),
  KEY `ix_job_applications_user_id` (`user_id`),
  KEY `ix_job_applications_resume_version_id` (`resume_version_id`),
  CONSTRAINT `job_applications_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `job_applications_ibfk_2` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `job_applications_ibfk_3` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `job_applications_ibfk_4` FOREIGN KEY (`resume_version_id`) REFERENCES `resume_versions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_applications`
--

LOCK TABLES `job_applications` WRITE;
/*!40000 ALTER TABLE `job_applications` DISABLE KEYS */;
/*!40000 ALTER TABLE `job_applications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_descriptions`
--

DROP TABLE IF EXISTS `job_descriptions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_descriptions` (
  `primary_resume_id` int DEFAULT NULL,
  `source_url` varchar(1024) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_site` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_job_id` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `captured_at` datetime DEFAULT NULL,
  `status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'saved',
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `title` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `company` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `file_path` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `content_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `document_size` int NOT NULL DEFAULT '0',
  `parse_status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `raw_text` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `structured_data` json DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_job_source` (`user_id`,`source_site`,`source_job_id`),
  KEY `ix_job_descriptions_parse_status` (`parse_status`),
  KEY `ix_job_descriptions_content_hash` (`content_hash`),
  KEY `ix_job_descriptions_user_id` (`user_id`),
  KEY `ix_job_descriptions_primary_resume_id` (`primary_resume_id`),
  CONSTRAINT `job_descriptions_ibfk_1` FOREIGN KEY (`primary_resume_id`) REFERENCES `resumes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `job_descriptions_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_descriptions`
--

LOCK TABLES `job_descriptions` WRITE;
/*!40000 ALTER TABLE `job_descriptions` DISABLE KEYS */;
INSERT INTO `job_descriptions` VALUES (NULL,NULL,NULL,NULL,NULL,'saved',1,1,'Engineer','','','','',0,'pending','Build APIs',NULL,'2026-10-30 03:34:17','2026-10-30 03:34:17');
/*!40000 ALTER TABLE `job_descriptions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `llm_usage_events`
--

DROP TABLE IF EXISTS `llm_usage_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `llm_usage_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `task` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `model` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `base_url` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL,
  `prompt_tokens` int NOT NULL,
  `completion_tokens` int NOT NULL,
  `total_tokens` int NOT NULL,
  `success` tinyint(1) NOT NULL,
  `error_type` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL,
  `elapsed_ms` int NOT NULL,
  `called_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_llm_usage_events_called_at` (`called_at`),
  KEY `ix_llm_usage_events_success` (`success`),
  KEY `ix_llm_usage_events_user_id` (`user_id`),
  KEY `ix_llm_usage_events_task` (`task`),
  CONSTRAINT `llm_usage_events_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `llm_usage_events`
--

LOCK TABLES `llm_usage_events` WRITE;
/*!40000 ALTER TABLE `llm_usage_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `llm_usage_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `match_results`
--

DROP TABLE IF EXISTS `match_results`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `match_results` (
  `id` int NOT NULL AUTO_INCREMENT,
  `job_id` int NOT NULL,
  `candidate_id` int NOT NULL,
  `resume_id` int NOT NULL,
  `jd_id` int DEFAULT NULL,
  `overall_score` float NOT NULL,
  `recommendation` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `reason` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `dimension_scores` json NOT NULL,
  `matched_skills` json NOT NULL,
  `missing_skills` json NOT NULL,
  `strengths` json NOT NULL,
  `gaps` json NOT NULL,
  `report_json` json NOT NULL DEFAULT (_utf8mb4'{}'),
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_match_job_candidate` (`job_id`,`candidate_id`),
  KEY `ix_match_results_recommendation` (`recommendation`),
  KEY `ix_match_results_candidate_id` (`candidate_id`),
  KEY `ix_match_results_jd_id` (`jd_id`),
  KEY `ix_match_results_job_id` (`job_id`),
  KEY `ix_match_results_resume_id` (`resume_id`),
  CONSTRAINT `match_results_ibfk_1` FOREIGN KEY (`job_id`) REFERENCES `analysis_jobs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `match_results_ibfk_2` FOREIGN KEY (`candidate_id`) REFERENCES `analysis_candidates` (`id`) ON DELETE CASCADE,
  CONSTRAINT `match_results_ibfk_3` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `match_results_ibfk_4` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `match_results`
--

LOCK TABLES `match_results` WRITE;
/*!40000 ALTER TABLE `match_results` DISABLE KEYS */;
/*!40000 ALTER TABLE `match_results` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `profile_facts`
--

DROP TABLE IF EXISTS `profile_facts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `profile_facts` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `fact_key` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `kind` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content` json NOT NULL,
  `source_document_id` int DEFAULT NULL,
  `revision` int NOT NULL,
  `confirmed_at` datetime DEFAULT NULL,
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_profile_fact_revision` (`user_id`,`fact_key`,`revision`),
  KEY `source_document_id` (`source_document_id`),
  KEY `ix_profile_facts_user_id` (`user_id`),
  CONSTRAINT `profile_facts_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `profile_facts_ibfk_2` FOREIGN KEY (`source_document_id`) REFERENCES `resumes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `ck_profile_fact_revision` CHECK ((`revision` > 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `profile_facts`
--

LOCK TABLES `profile_facts` WRITE;
/*!40000 ALTER TABLE `profile_facts` DISABLE KEYS */;
/*!40000 ALTER TABLE `profile_facts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `resume_versions`
--

DROP TABLE IF EXISTS `resume_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `resume_versions` (
  `id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int NOT NULL,
  `run_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `resume_id` int DEFAULT NULL,
  `jd_id` int DEFAULT NULL,
  `parent_version_id` varchar(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `revision` int NOT NULL,
  `structured_content` json NOT NULL,
  `fact_refs` json NOT NULL,
  `status` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `parent_version_id` (`parent_version_id`),
  KEY `ix_resume_versions_resume_id` (`resume_id`),
  KEY `ix_resume_versions_user_id` (`user_id`),
  KEY `ix_resume_versions_jd_id` (`jd_id`),
  KEY `ix_resume_versions_run_id` (`run_id`),
  CONSTRAINT `resume_versions_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `resume_versions_ibfk_2` FOREIGN KEY (`run_id`) REFERENCES `agent_runs` (`id`) ON DELETE SET NULL,
  CONSTRAINT `resume_versions_ibfk_3` FOREIGN KEY (`resume_id`) REFERENCES `resumes` (`id`) ON DELETE SET NULL,
  CONSTRAINT `resume_versions_ibfk_4` FOREIGN KEY (`jd_id`) REFERENCES `job_descriptions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `resume_versions_ibfk_5` FOREIGN KEY (`parent_version_id`) REFERENCES `resume_versions` (`id`) ON DELETE SET NULL,
  CONSTRAINT `ck_resume_version_revision` CHECK ((`revision` > 0)),
  CONSTRAINT `version_status` CHECK ((`status` in (_utf8mb4'draft',_utf8mb4'confirmed')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `resume_versions`
--

LOCK TABLES `resume_versions` WRITE;
/*!40000 ALTER TABLE `resume_versions` DISABLE KEYS */;
INSERT INTO `resume_versions` VALUES ('delivery-confirmed',1,NULL,1,1,NULL,3,'{\"resume\": {\"skills\": [{\"name\": \"Python\", \"category\": \"后端\", \"proficiency_claim\": \"可独立开发业务接口\"}, {\"name\": \"TypeScript / Vue\", \"category\": \"前端\"}, {\"name\": \"SQL\", \"category\": \"数据建模\"}], \"contact\": {\"email\": \"lin.zhiyuan@example.test\", \"phone\": \"13800000000\", \"location\": \"上海\"}, \"quality\": {\"internal_marker\": \"internal_only_marker\"}, \"projects\": [{\"name\": \"ResuMate 求职材料协作\", \"role\": \"全栈开发\", \"bullets\": [{\"raw_text\": \"项目独立要点：将开发决策与测试过程整理成教学文档。\"}], \"duration\": \"2026.09 - 2026.10\", \"description\": \"建立岗位资料、简历版本、来源引用和用户审阅流程。保留固定输入及历史投递材料，支持取消、补问、并发保存与失败重试。为桌面和手机验证长文、错误与空状态，逐张检查真实页面截图。建立岗位资料、简历版本、来源引用和用户审阅流程。保留固定输入及历史投递材料，支持取消、补问、并发保存与失败重试。为桌面和手机验证长文、错误与空状态，逐张检查真实页面截图。建立岗位资料、简历版本、来源引用和用户审阅流程。保留固定输入及历史投递材料，支持取消、补问、并发保存与失败重试。为桌面和手机验证长文、错误与空状态，逐张检查真实页面截图。\", \"technologies\": [\"TypeScript\", \"Celery\", \"Redis\", \"Playwright\"]}, {\"name\": \"已清空描述的练习项目\", \"role\": \"协作者\", \"bullets\": [{\"raw_text\": \"已清空旧正文不应出现\"}], \"description\": \"\"}], \"education\": [{\"gpa\": \"3.7 / 4.0\", \"lab\": \"软件系统实验室\", \"rank\": \"前 10%\", \"major\": \"软件工程\", \"years\": \"2020 - 2024\", \"degree\": \"本科\", \"papers\": [\"面向协作流程的任务恢复实践\"], \"school\": \"示例科技大学\", \"advisor\": \"陈老师\", \"college\": \"计算机学院\", \"courses\": [\"数据库系统\", \"计算机网络\"], \"achievements\": [\"优秀毕业设计\"], \"research_direction\": \"分布式应用\"}], \"languages\": [\"中文：母语\", \"英语：技术文档阅读\"], \"source_refs\": [{\"text\": \"internal_only_marker\"}], \"achievements\": [{\"name\": \"校园软件设计实践奖\", \"level\": \"校级\", \"category\": \"工程实践\"}], \"self_summary\": \"全栈开发工程师，关注可靠的业务流程、可解释的 AI 工具与清晰的产品体验。参与接口设计、数据建模、前后端联调和自动化测试，以能够复现的证据记录交付结果。\", \"candidate_name\": \"林知远\", \"certifications\": [\"软件设计师\"], \"work_experience\": [{\"title\": \"全栈开发工程师\", \"bullets\": [{\"raw_text\": \"独立要点：维护接口说明与新成员联调指引。\"}], \"company\": \"示例企业数字化与智能协作平台研发中心（业务系统与开发者体验团队）\", \"metrics\": [{\"name\": \"吞吐\", \"value\": \"3倍\"}], \"duration\": \"2024.07 - 至今\", \"description\": \"负责接口契约和数据库结构设计，与产品及前端同事核对异常路径。将长任务移至独立工作进程，保存进度与可恢复的任务状态。为实际出现的故障补充回归，记录问题、原因和修复证据。负责接口契约和数据库结构设计，与产品及前端同事核对异常路径。将长任务移至独立工作进程，保存进度与可恢复的任务状态。为实际出现的故障补充回归，记录问题、原因和修复证据。负责接口契约和数据库结构设计，与产品及前端同事核对异常路径。将长任务移至独立工作进程，保存进度与可恢复的任务状态。为实际出现的故障补充回归，记录问题、原因和修复证据。\", \"technologies\": [\"Python\", \"FastAPI\", \"Vue\", \"MySQL\"]}, {\"title\": \"开发实习生\", \"bullets\": [{\"raw_text\": \"旧要点不应复活\"}], \"company\": \"校园信息服务团队\", \"metrics\": [{\"raw_text\": \"旧指标不应复活\"}], \"duration\": \"2023.07 - 2024.06\", \"description\": \"已审阅后的表述：参与信息查询页面与服务接口开发，维护可重复运行的联调样例。\"}]}, \"changes\": [{\"status\": \"edited\", \"section\": \"/work_experience/1/description\", \"editedText\": \"已审阅后的表述：参与信息查询页面与服务接口开发，维护可重复运行的联调样例。\"}, {\"status\": \"edited\", \"section\": \"/projects/1/description\", \"editedText\": \"\"}]}','[]','confirmed','2026-10-30 03:34:17');
/*!40000 ALTER TABLE `resume_versions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `resumes`
--

DROP TABLE IF EXISTS `resumes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `resumes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `filename` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `file_path` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL,
  `content_hash` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '',
  `document_size` int NOT NULL DEFAULT '0',
  `parse_status` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `raw_text` longtext COLLATE utf8mb4_unicode_ci NOT NULL,
  `structured_data` json DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_resumes_user_id` (`user_id`),
  KEY `ix_resumes_content_hash` (`content_hash`),
  KEY `ix_resumes_parse_status` (`parse_status`),
  CONSTRAINT `resumes_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `resumes`
--

LOCK TABLES `resumes` WRITE;
/*!40000 ALTER TABLE `resumes` DISABLE KEYS */;
INSERT INTO `resumes` VALUES (1,1,'delivery-original.txt','/app/data/documents/delivery-original.txt','',0,'pending','Synthetic original resume: API development','{\"self_summary\": \"API development\"}','2026-10-30 03:34:17','2026-10-30 03:34:17');
/*!40000 ALTER TABLE `resumes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tool_operations`
--

DROP TABLE IF EXISTS `tool_operations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tool_operations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `run_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `operation_key` varchar(160) COLLATE utf8mb4_unicode_ci NOT NULL,
  `tool_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(9) COLLATE utf8mb4_unicode_ci NOT NULL,
  `result_ref` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tool_operation_key` (`run_id`,`operation_key`),
  CONSTRAINT `tool_operations_ibfk_1` FOREIGN KEY (`run_id`) REFERENCES `agent_runs` (`id`) ON DELETE CASCADE,
  CONSTRAINT `tool_operation_status` CHECK ((`status` in (_utf8mb4'pending',_utf8mb4'succeeded',_utf8mb4'failed')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tool_operations`
--

LOCK TABLES `tool_operations` WRITE;
/*!40000 ALTER TABLE `tool_operations` DISABLE KEYS */;
/*!40000 ALTER TABLE `tool_operations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_llm_settings`
--

DROP TABLE IF EXISTS `user_llm_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_llm_settings` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `api_key` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `base_url` varchar(1024) COLLATE utf8mb4_unicode_ci NOT NULL,
  `model` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `max_tokens` int DEFAULT NULL,
  `context_window_tokens` int DEFAULT NULL,
  `request_timeout_seconds` float DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `updated_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_user_llm_settings_user_id` (`user_id`),
  CONSTRAINT `user_llm_settings_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_llm_settings`
--

LOCK TABLES `user_llm_settings` WRITE;
/*!40000 ALTER TABLE `user_llm_settings` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_llm_settings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_username` (`username`),
  KEY `ix_users_id` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'delivery-user','not-a-login','user','2026-10-30 03:34:17');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping events for database 'resumate'
--

--
-- Dumping routines for database 'resumate'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-30  3:34:50
