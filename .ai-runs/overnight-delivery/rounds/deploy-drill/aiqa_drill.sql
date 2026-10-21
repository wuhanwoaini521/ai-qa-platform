--
-- PostgreSQL database dump
--

\restrict 3x1RcwOSkDssnTYxtfFPhJhJ47W9J2ylVaYymdnbx0IHR4Ojpnr17r5pk2SflxF

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agent_task_artifacts; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.agent_task_artifacts (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    step_id character varying(36),
    artifact_id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    kind character varying(50) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.agent_task_artifacts OWNER TO aiqa;

--
-- Name: agent_task_decisions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.agent_task_decisions (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    step_id character varying(36),
    name character varying(128) NOT NULL,
    provider character varying(100) NOT NULL,
    choice character varying(128) NOT NULL,
    confidence double precision NOT NULL,
    rationale text NOT NULL,
    escalated boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.agent_task_decisions OWNER TO aiqa;

--
-- Name: agent_task_events; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.agent_task_events (
    id integer NOT NULL,
    task_id character varying(36) NOT NULL,
    type character varying(64) NOT NULL,
    payload text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    step_id character varying(36)
);


ALTER TABLE public.agent_task_events OWNER TO aiqa;

--
-- Name: agent_task_events_id_seq; Type: SEQUENCE; Schema: public; Owner: aiqa
--

CREATE SEQUENCE public.agent_task_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.agent_task_events_id_seq OWNER TO aiqa;

--
-- Name: agent_task_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: aiqa
--

ALTER SEQUENCE public.agent_task_events_id_seq OWNED BY public.agent_task_events.id;


--
-- Name: agent_task_evidence; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.agent_task_evidence (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    step_id character varying(36),
    type character varying(50) NOT NULL,
    source character varying(200) NOT NULL,
    summary text NOT NULL,
    content text,
    artifact_id character varying(36),
    metadata_json text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.agent_task_evidence OWNER TO aiqa;

--
-- Name: agent_task_steps; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.agent_task_steps (
    id character varying(36) NOT NULL,
    task_id character varying(36) NOT NULL,
    "position" integer NOT NULL,
    key character varying(100) NOT NULL,
    name character varying(200) NOT NULL,
    tool character varying(128) NOT NULL,
    status character varying(40) NOT NULL,
    dependencies text NOT NULL,
    condition text NOT NULL,
    inputs text NOT NULL,
    outputs text NOT NULL,
    evidence_ids text NOT NULL,
    decision text,
    retry_count integer NOT NULL,
    max_retries integer NOT NULL,
    parallelizable boolean NOT NULL,
    error text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    duration_ms double precision NOT NULL
);


ALTER TABLE public.agent_task_steps OWNER TO aiqa;

--
-- Name: agent_tasks; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.agent_tasks (
    id character varying(36) NOT NULL,
    type character varying(40) NOT NULL,
    goal text NOT NULL,
    status character varying(32) NOT NULL,
    owner_id character varying(36) NOT NULL,
    project_id character varying(36),
    workspace_id character varying(36),
    inputs text NOT NULL,
    context text NOT NULL,
    verification text NOT NULL,
    retry_count integer NOT NULL,
    replan_count integer NOT NULL,
    max_steps integer NOT NULL,
    max_retries integer NOT NULL,
    max_replans integer NOT NULL,
    max_ai_calls integer NOT NULL,
    max_duration_seconds integer NOT NULL,
    current_step_id character varying(36),
    failure_reason text,
    created_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    updated_at timestamp with time zone NOT NULL,
    lease_owner character varying(120),
    lease_token integer DEFAULT 0 NOT NULL,
    lease_expires_at timestamp with time zone
);


ALTER TABLE public.agent_tasks OWNER TO aiqa;

--
-- Name: ai_daily_budgets; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.ai_daily_budgets (
    day character varying(10) NOT NULL,
    reserved_requests integer NOT NULL
);


ALTER TABLE public.ai_daily_budgets OWNER TO aiqa;

--
-- Name: ai_invocations; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.ai_invocations (
    id character varying(36) NOT NULL,
    request_id character varying(128),
    task_id character varying(128),
    run_id character varying(128),
    task character varying(100) NOT NULL,
    provider character varying(100) NOT NULL,
    model character varying(100) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    duration_ms double precision NOT NULL,
    input_tokens integer,
    output_tokens integer,
    retry_count integer NOT NULL,
    fallback_used boolean NOT NULL,
    status character varying(50) NOT NULL,
    error_type character varying(100),
    prompt_version character varying(50),
    token_source character varying(20) NOT NULL,
    decision_name character varying(128),
    decision_choice character varying(128),
    decision_confidence double precision,
    created_at timestamp with time zone NOT NULL,
    decision_value double precision,
    locator_repair_id character varying(36),
    step_id character varying(36)
);


ALTER TABLE public.ai_invocations OWNER TO aiqa;

--
-- Name: ai_provider_configs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.ai_provider_configs (
    id character varying(50) NOT NULL,
    provider character varying(50) NOT NULL,
    encrypted_api_key text,
    model character varying(128) NOT NULL,
    base_url character varying(2048) NOT NULL,
    timeout double precision NOT NULL,
    max_retries integer NOT NULL,
    max_request_tokens integer NOT NULL,
    max_daily_requests integer NOT NULL,
    max_task_calls integer NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.ai_provider_configs OWNER TO aiqa;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.alembic_version (
    version_num character varying(128) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO aiqa;

--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.api_keys (
    id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    name character varying(100) NOT NULL,
    key_prefix character varying(20) NOT NULL,
    key_hash character varying(128) NOT NULL,
    expires_at timestamp with time zone,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.api_keys OWNER TO aiqa;

--
-- Name: automation_bindings; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.automation_bindings (
    id character varying(36) NOT NULL,
    test_case_id character varying(36) NOT NULL,
    workspace_id character varying(36) NOT NULL,
    nodeid character varying(500) NOT NULL,
    file_path character varying(500) NOT NULL,
    framework character varying(50) NOT NULL,
    status character varying(50) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    recorder_evidence_bundle text
);


ALTER TABLE public.automation_bindings OWNER TO aiqa;

--
-- Name: breakpoints; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.breakpoints (
    id character varying(36) NOT NULL,
    workspace_id character varying(36) NOT NULL,
    file_path character varying(500) NOT NULL,
    line_number integer NOT NULL,
    enabled boolean NOT NULL,
    source character varying(30) NOT NULL,
    run_id character varying(36),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.breakpoints OWNER TO aiqa;

--
-- Name: browser_sessions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.browser_sessions (
    id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    case_execution_id character varying(36),
    worker_id character varying(100) NOT NULL,
    browser_session_id character varying(36) NOT NULL,
    page_id character varying(36) NOT NULL,
    nodeid character varying(500) NOT NULL,
    case_name character varying(250) NOT NULL,
    current_url character varying(2048) NOT NULL,
    page_evidence_json text,
    status character varying(30) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    failure_snapshot_json text,
    encrypted_storage_state text,
    storage_state_expires_at timestamp with time zone
);


ALTER TABLE public.browser_sessions OWNER TO aiqa;

--
-- Name: debug_sessions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.debug_sessions (
    id character varying(36) NOT NULL,
    owner_id character varying(36) NOT NULL,
    workspace_id character varying(36) NOT NULL,
    nodeid character varying(1000) NOT NULL,
    run_id character varying(36),
    execution_id character varying(36),
    failure_id character varying(36),
    status character varying(30) DEFAULT 'STARTING'::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone
);


ALTER TABLE public.debug_sessions OWNER TO aiqa;

--
-- Name: decision_provider_configs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.decision_provider_configs (
    provider character varying(50) NOT NULL,
    enabled boolean NOT NULL,
    encrypted_api_key text,
    model character varying(128) NOT NULL,
    base_url character varying(2048) NOT NULL,
    timeout double precision NOT NULL,
    minimum_confidence double precision NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.decision_provider_configs OWNER TO aiqa;

--
-- Name: discovery_evidence; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.discovery_evidence (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    kind character varying(30) NOT NULL,
    evidence_id character varying(120) NOT NULL,
    dedupe_key character varying(600) NOT NULL,
    state_id character varying(64),
    step_id character varying(120),
    artifact_id character varying(36),
    source character varying(40) NOT NULL,
    redacted boolean NOT NULL,
    payload text NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.discovery_evidence OWNER TO aiqa;

--
-- Name: discovery_scenarios; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.discovery_scenarios (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    scenario_id character varying(120) NOT NULL,
    title character varying(300) NOT NULL,
    url_template character varying(600) NOT NULL,
    evidence_ids text NOT NULL,
    test_case_ids text NOT NULL,
    coverage_status character varying(30) NOT NULL,
    match_method character varying(40),
    note text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.discovery_scenarios OWNER TO aiqa;

--
-- Name: discovery_suggestions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.discovery_suggestions (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    suggestion_id character varying(120) NOT NULL,
    scenario_id character varying(120) NOT NULL,
    source character varying(20) NOT NULL,
    provider character varying(100) NOT NULL,
    model character varying(100) NOT NULL,
    analysis_status character varying(30) NOT NULL,
    review_status character varying(30) NOT NULL,
    input_hash character varying(64) NOT NULL,
    attempts integer NOT NULL,
    task_id character varying(128),
    invocation_id character varying(36),
    evidence_ids text NOT NULL,
    related_case_ids text NOT NULL,
    payload text NOT NULL,
    jev text NOT NULL,
    review text NOT NULL,
    duration_ms double precision,
    input_tokens integer,
    output_tokens integer,
    token_source character varying(20) NOT NULL,
    error_type character varying(60),
    error_detail text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.discovery_suggestions OWNER TO aiqa;

--
-- Name: execution_jobs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.execution_jobs (
    id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    workspace_id character varying(36) NOT NULL,
    nodeids text NOT NULL,
    runner_type character varying(50) NOT NULL,
    browser character varying(50) NOT NULL,
    priority integer NOT NULL,
    status character varying(50) NOT NULL,
    assigned_worker_id character varying(36),
    retry_count integer NOT NULL,
    max_retries integer NOT NULL,
    error_message text,
    duration_ms double precision NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.execution_jobs OWNER TO aiqa;

--
-- Name: external_artifact_references; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.external_artifact_references (
    id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    name character varying(200) NOT NULL,
    type character varying(50) NOT NULL,
    url character varying(1000) NOT NULL,
    metadata_json text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.external_artifact_references OWNER TO aiqa;

--
-- Name: failure_analyses; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.failure_analyses (
    id character varying(36) NOT NULL,
    failure_id character varying(36) NOT NULL,
    status character varying(30) NOT NULL,
    events text NOT NULL,
    result text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone
);


ALTER TABLE public.failure_analyses OWNER TO aiqa;

--
-- Name: failure_records; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.failure_records (
    id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    execution_id character varying(36) NOT NULL,
    test_nodeid character varying(500) NOT NULL,
    test_name character varying(250) NOT NULL,
    classification character varying(100) NOT NULL,
    exception_type character varying(200) NOT NULL,
    error_message text NOT NULL,
    stack_trace text NOT NULL,
    failing_locator character varying(500),
    screenshot_path character varying(500),
    trace_path character varying(500),
    dom_snapshot_path character varying(500),
    console_logs text NOT NULL,
    suggested_action text,
    repair_proposal text,
    evidence_bundle text,
    created_at timestamp with time zone NOT NULL,
    source_file character varying(500),
    source_line integer
);


ALTER TABLE public.failure_records OWNER TO aiqa;

--
-- Name: integration_audits; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.integration_audits (
    id character varying(36) NOT NULL,
    system character varying(50) NOT NULL,
    action character varying(100) NOT NULL,
    target_id character varying(200) NOT NULL,
    user_id character varying(100) NOT NULL,
    status character varying(50) NOT NULL,
    details text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.integration_audits OWNER TO aiqa;

--
-- Name: locator_history; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.locator_history (
    id character varying(64) NOT NULL,
    page_url character varying(2048) NOT NULL,
    locator character varying(1000) NOT NULL,
    success_count integer NOT NULL,
    failure_count integer NOT NULL,
    verification_count integer NOT NULL,
    heal_count integer NOT NULL,
    last_success_at timestamp with time zone,
    last_failure_at timestamp with time zone,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.locator_history OWNER TO aiqa;

--
-- Name: locator_repairs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.locator_repairs (
    id character varying(36) NOT NULL,
    failure_id character varying(36) NOT NULL,
    analysis_id character varying(36),
    state character varying(32) NOT NULL,
    block_reason character varying(128),
    candidate_id character varying(128),
    verification_run_id character varying(36),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    CONSTRAINT ck_locator_repairs_state CHECK (((state)::text = ANY ((ARRAY['CREATED'::character varying, 'ANALYZING'::character varying, 'DECIDING'::character varying, 'VERIFYING_CANDIDATE'::character varying, 'PATCH_READY'::character varying, 'APPLYING'::character varying, 'PATCH_APPLIED'::character varying, 'VERIFYING_FIX'::character varying, 'VERIFIED'::character varying, 'FAILED'::character varying, 'BLOCKED'::character varying, 'NOT_APPLICABLE'::character varying, 'ROLLED_BACK'::character varying])::text[])))
);


ALTER TABLE public.locator_repairs OWNER TO aiqa;

--
-- Name: projects; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.projects (
    id character varying(36) NOT NULL,
    name character varying(120) NOT NULL,
    description text NOT NULL,
    repository_url character varying(500),
    default_branch character varying(100) NOT NULL,
    framework_type character varying(50) NOT NULL,
    demo_kind character varying(50),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    owner_id character varying(36),
    team_id character varying(36)
);


ALTER TABLE public.projects OWNER TO aiqa;

--
-- Name: quality_discovery_runs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.quality_discovery_runs (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    requested_by character varying(100) NOT NULL,
    mode character varying(20) NOT NULL,
    start_url character varying(2048) NOT NULL,
    requirement_id character varying(36),
    requirement_text text NOT NULL,
    allowed_domains text NOT NULL,
    status character varying(30) NOT NULL,
    progress text NOT NULL,
    result text NOT NULL,
    error text,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL
);


ALTER TABLE public.quality_discovery_runs OWNER TO aiqa;

--
-- Name: releases; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.releases (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    version character varying(50) NOT NULL,
    name character varying(200) NOT NULL,
    description text NOT NULL,
    status character varying(50) NOT NULL,
    target_date character varying(50) NOT NULL,
    pass_rate_threshold double precision NOT NULL,
    max_allowed_flaky integer NOT NULL,
    quality_score double precision NOT NULL,
    blockers text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.releases OWNER TO aiqa;

--
-- Name: requirements; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.requirements (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    title character varying(200) NOT NULL,
    description text NOT NULL,
    acceptance_criteria text NOT NULL,
    qa_model text,
    status character varying(50) NOT NULL,
    external_system character varying(50),
    external_id character varying(100),
    external_url character varying(500),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.requirements OWNER TO aiqa;

--
-- Name: runner_profiles; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.runner_profiles (
    id character varying(36) NOT NULL,
    project_id character varying(36),
    name character varying(150) NOT NULL,
    type character varying(50) NOT NULL,
    enabled boolean NOT NULL,
    config text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.runner_profiles OWNER TO aiqa;

--
-- Name: security_audits; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.security_audits (
    id character varying(36) NOT NULL,
    action character varying(100) NOT NULL,
    actor_id character varying(100) NOT NULL,
    actor_email character varying(255) NOT NULL,
    target_resource character varying(255) NOT NULL,
    ip_address character varying(50) NOT NULL,
    status character varying(50) NOT NULL,
    details text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.security_audits OWNER TO aiqa;

--
-- Name: stored_artifacts; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.stored_artifacts (
    id character varying(36) NOT NULL,
    filename character varying(255) NOT NULL,
    size_bytes integer NOT NULL,
    content_type character varying(100) NOT NULL,
    storage_type character varying(50) NOT NULL,
    storage_path character varying(1000) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    project_id character varying(36),
    created_by character varying(100)
);


ALTER TABLE public.stored_artifacts OWNER TO aiqa;

--
-- Name: team_members; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.team_members (
    id character varying(36) NOT NULL,
    team_id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    role character varying(50) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


ALTER TABLE public.team_members OWNER TO aiqa;

--
-- Name: teams; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.teams (
    id character varying(36) NOT NULL,
    name character varying(150) NOT NULL,
    description text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.teams OWNER TO aiqa;

--
-- Name: test_cases; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.test_cases (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    requirement_id character varying(36),
    test_design_id character varying(36),
    title character varying(250) NOT NULL,
    preconditions text NOT NULL,
    steps text NOT NULL,
    expected_result text NOT NULL,
    test_model text,
    priority character varying(10) NOT NULL,
    automation_status character varying(50) NOT NULL,
    tags text NOT NULL,
    external_system character varying(50),
    external_case_id character varying(100),
    external_url character varying(500),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.test_cases OWNER TO aiqa;

--
-- Name: test_designs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.test_designs (
    id character varying(36) NOT NULL,
    requirement_id character varying(36) NOT NULL,
    title character varying(200) NOT NULL,
    category character varying(50) NOT NULL,
    description text NOT NULL,
    risk character varying(100) NOT NULL,
    scenario_model text,
    status character varying(50) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.test_designs OWNER TO aiqa;

--
-- Name: test_executions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.test_executions (
    id character varying(36) NOT NULL,
    run_id character varying(36) NOT NULL,
    nodeid character varying(500) NOT NULL,
    status character varying(50) NOT NULL,
    duration_ms double precision NOT NULL,
    retry_count integer NOT NULL,
    error_message text,
    stack_trace text,
    failure_category character varying(100),
    artifact_paths text NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    timestamp_source character varying(20)
);


ALTER TABLE public.test_executions OWNER TO aiqa;

--
-- Name: test_runs; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.test_runs (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    workspace_id character varying(36) NOT NULL,
    status character varying(50) NOT NULL,
    requested_by character varying(100) NOT NULL,
    runner_type character varying(50) NOT NULL,
    runner_profile_id character varying(36),
    external_job_id character varying(200),
    external_build_url character varying(500),
    queue_duration_ms double precision NOT NULL,
    environment text NOT NULL,
    browser character varying(50) NOT NULL,
    parallel_workers integer NOT NULL,
    markers text NOT NULL,
    nodeids text NOT NULL,
    total integer NOT NULL,
    passed integer NOT NULL,
    failed integer NOT NULL,
    skipped integer NOT NULL,
    cancelled integer NOT NULL,
    duration_ms double precision NOT NULL,
    log_output text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    task_id character varying(36),
    parent_run_id character varying(36),
    origin_failure_id character varying(36)
);


ALTER TABLE public.test_runs OWNER TO aiqa;

--
-- Name: users; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.users (
    id character varying(36) NOT NULL,
    email character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(50) NOT NULL,
    is_active boolean NOT NULL,
    avatar_url character varying(500),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.users OWNER TO aiqa;

--
-- Name: workers; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.workers (
    id character varying(36) NOT NULL,
    hostname character varying(255) NOT NULL,
    ip_address character varying(50) NOT NULL,
    status character varying(50) NOT NULL,
    browsers text NOT NULL,
    os character varying(50) NOT NULL,
    max_concurrency integer NOT NULL,
    current_load integer NOT NULL,
    tags text NOT NULL,
    last_heartbeat_at timestamp with time zone NOT NULL,
    registered_at timestamp with time zone NOT NULL
);


ALTER TABLE public.workers OWNER TO aiqa;

--
-- Name: workflow_definition_versions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.workflow_definition_versions (
    id character varying(36) NOT NULL,
    definition_id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    version integer NOT NULL,
    state character varying(20) NOT NULL,
    graph text NOT NULL,
    checksum character varying(64) NOT NULL,
    issues text NOT NULL,
    created_by character varying(36),
    created_at timestamp with time zone NOT NULL,
    published_by character varying(36),
    published_at timestamp with time zone
);


ALTER TABLE public.workflow_definition_versions OWNER TO aiqa;

--
-- Name: workflow_definitions; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.workflow_definitions (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    name character varying(200) NOT NULL,
    description text NOT NULL,
    published_version integer,
    draft_version integer,
    version integer DEFAULT 1 NOT NULL,
    created_by character varying(36),
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.workflow_definitions OWNER TO aiqa;

--
-- Name: workspaces; Type: TABLE; Schema: public; Owner: aiqa
--

CREATE TABLE public.workspaces (
    id character varying(36) NOT NULL,
    project_id character varying(36) NOT NULL,
    path character varying(500) NOT NULL,
    branch character varying(100) NOT NULL,
    status character varying(50) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.workspaces OWNER TO aiqa;

--
-- Name: agent_task_events id; Type: DEFAULT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_events ALTER COLUMN id SET DEFAULT nextval('public.agent_task_events_id_seq'::regclass);


--
-- Data for Name: agent_task_artifacts; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.agent_task_artifacts (id, task_id, step_id, artifact_id, name, kind, created_at) FROM stdin;
\.


--
-- Data for Name: agent_task_decisions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.agent_task_decisions (id, task_id, step_id, name, provider, choice, confidence, rationale, escalated, created_at) FROM stdin;
\.


--
-- Data for Name: agent_task_events; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.agent_task_events (id, task_id, type, payload, created_at, step_id) FROM stdin;
\.


--
-- Data for Name: agent_task_evidence; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.agent_task_evidence (id, task_id, step_id, type, source, summary, content, artifact_id, metadata_json, created_at) FROM stdin;
\.


--
-- Data for Name: agent_task_steps; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.agent_task_steps (id, task_id, "position", key, name, tool, status, dependencies, condition, inputs, outputs, evidence_ids, decision, retry_count, max_retries, parallelizable, error, started_at, finished_at, duration_ms) FROM stdin;
\.


--
-- Data for Name: agent_tasks; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.agent_tasks (id, type, goal, status, owner_id, project_id, workspace_id, inputs, context, verification, retry_count, replan_count, max_steps, max_retries, max_replans, max_ai_calls, max_duration_seconds, current_step_id, failure_reason, created_at, started_at, finished_at, updated_at, lease_owner, lease_token, lease_expires_at) FROM stdin;
\.


--
-- Data for Name: ai_daily_budgets; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.ai_daily_budgets (day, reserved_requests) FROM stdin;
\.


--
-- Data for Name: ai_invocations; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.ai_invocations (id, request_id, task_id, run_id, task, provider, model, started_at, duration_ms, input_tokens, output_tokens, retry_count, fallback_used, status, error_type, prompt_version, token_source, decision_name, decision_choice, decision_confidence, created_at, decision_value, locator_repair_id, step_id) FROM stdin;
\.


--
-- Data for Name: ai_provider_configs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.ai_provider_configs (id, provider, encrypted_api_key, model, base_url, timeout, max_retries, max_request_tokens, max_daily_requests, max_task_calls, updated_at) FROM stdin;
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.alembic_version (version_num) FROM stdin;
0021_artifact_actor_width
\.


--
-- Data for Name: api_keys; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.api_keys (id, user_id, name, key_prefix, key_hash, expires_at, last_used_at, created_at) FROM stdin;
\.


--
-- Data for Name: automation_bindings; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.automation_bindings (id, test_case_id, workspace_id, nodeid, file_path, framework, status, created_at, updated_at, recorder_evidence_bundle) FROM stdin;
\.


--
-- Data for Name: breakpoints; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.breakpoints (id, workspace_id, file_path, line_number, enabled, source, run_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: browser_sessions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.browser_sessions (id, run_id, case_execution_id, worker_id, browser_session_id, page_id, nodeid, case_name, current_url, page_evidence_json, status, started_at, finished_at, failure_snapshot_json, encrypted_storage_state, storage_state_expires_at) FROM stdin;
\.


--
-- Data for Name: debug_sessions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.debug_sessions (id, owner_id, workspace_id, nodeid, run_id, execution_id, failure_id, status, created_at, closed_at) FROM stdin;
\.


--
-- Data for Name: decision_provider_configs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.decision_provider_configs (provider, enabled, encrypted_api_key, model, base_url, timeout, minimum_confidence, updated_at) FROM stdin;
\.


--
-- Data for Name: discovery_evidence; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.discovery_evidence (id, project_id, run_id, kind, evidence_id, dedupe_key, state_id, step_id, artifact_id, source, redacted, payload, observed_at, created_at) FROM stdin;
\.


--
-- Data for Name: discovery_scenarios; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.discovery_scenarios (id, project_id, run_id, scenario_id, title, url_template, evidence_ids, test_case_ids, coverage_status, match_method, note, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: discovery_suggestions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.discovery_suggestions (id, project_id, run_id, suggestion_id, scenario_id, source, provider, model, analysis_status, review_status, input_hash, attempts, task_id, invocation_id, evidence_ids, related_case_ids, payload, jev, review, duration_ms, input_tokens, output_tokens, token_source, error_type, error_detail, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: execution_jobs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.execution_jobs (id, run_id, project_id, workspace_id, nodeids, runner_type, browser, priority, status, assigned_worker_id, retry_count, max_retries, error_message, duration_ms, started_at, finished_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: external_artifact_references; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.external_artifact_references (id, run_id, name, type, url, metadata_json, created_at) FROM stdin;
\.


--
-- Data for Name: failure_analyses; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.failure_analyses (id, failure_id, status, events, result, created_at, finished_at) FROM stdin;
\.


--
-- Data for Name: failure_records; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.failure_records (id, run_id, execution_id, test_nodeid, test_name, classification, exception_type, error_message, stack_trace, failing_locator, screenshot_path, trace_path, dom_snapshot_path, console_logs, suggested_action, repair_proposal, evidence_bundle, created_at, source_file, source_line) FROM stdin;
\.


--
-- Data for Name: integration_audits; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.integration_audits (id, system, action, target_id, user_id, status, details, created_at) FROM stdin;
\.


--
-- Data for Name: locator_history; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.locator_history (id, page_url, locator, success_count, failure_count, verification_count, heal_count, last_success_at, last_failure_at, updated_at) FROM stdin;
\.


--
-- Data for Name: locator_repairs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.locator_repairs (id, failure_id, analysis_id, state, block_reason, candidate_id, verification_run_id, created_at, updated_at, finished_at) FROM stdin;
\.


--
-- Data for Name: projects; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.projects (id, name, description, repository_url, default_branch, framework_type, demo_kind, created_at, updated_at, owner_id, team_id) FROM stdin;
proj_391aeb3ef389	Drill project	created by the Round 20 deployment drill	\N	main	playwright_python	\N	2026-10-21 12:46:38.793597+00	2026-10-21 12:46:38.793597+00	ea2bf9a3-5c64-4429-9505-c65451621b09	\N
\.


--
-- Data for Name: quality_discovery_runs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.quality_discovery_runs (id, project_id, requested_by, mode, start_url, requirement_id, requirement_text, allowed_domains, status, progress, result, error, created_at, updated_at, finished_at, version) FROM stdin;
\.


--
-- Data for Name: releases; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.releases (id, project_id, version, name, description, status, target_date, pass_rate_threshold, max_allowed_flaky, quality_score, blockers, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: requirements; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.requirements (id, project_id, title, description, acceptance_criteria, qa_model, status, external_system, external_id, external_url, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: runner_profiles; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.runner_profiles (id, project_id, name, type, enabled, config, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: security_audits; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.security_audits (id, action, actor_id, actor_email, target_resource, ip_address, status, details, created_at) FROM stdin;
1e21c5df-afc0-48b5-852c-f411b3596d76	LOGIN	ea2bf9a3-5c64-4429-9505-c65451621b09	admin@ai-qa.local	auth	172.20.0.1	SUCCESS	{"role": "ADMIN"}	2026-10-21 12:46:38.724706+00
\.


--
-- Data for Name: stored_artifacts; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.stored_artifacts (id, filename, size_bytes, content_type, storage_type, storage_path, created_at, project_id, created_by) FROM stdin;
\.


--
-- Data for Name: team_members; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.team_members (id, team_id, user_id, role, created_at) FROM stdin;
\.


--
-- Data for Name: teams; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.teams (id, name, description, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: test_cases; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.test_cases (id, project_id, requirement_id, test_design_id, title, preconditions, steps, expected_result, test_model, priority, automation_status, tags, external_system, external_case_id, external_url, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: test_designs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.test_designs (id, requirement_id, title, category, description, risk, scenario_model, status, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: test_executions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.test_executions (id, run_id, nodeid, status, duration_ms, retry_count, error_message, stack_trace, failure_category, artifact_paths, started_at, finished_at, timestamp_source) FROM stdin;
\.


--
-- Data for Name: test_runs; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.test_runs (id, project_id, workspace_id, status, requested_by, runner_type, runner_profile_id, external_job_id, external_build_url, queue_duration_ms, environment, browser, parallel_workers, markers, nodeids, total, passed, failed, skipped, cancelled, duration_ms, log_output, started_at, finished_at, created_at, task_id, parent_run_id, origin_failure_id) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.users (id, email, full_name, password_hash, role, is_active, avatar_url, created_at, updated_at) FROM stdin;
ea2bf9a3-5c64-4429-9505-c65451621b09	admin@ai-qa.local	Enterprise Admin	749f09bade8aca755660eeb17792da880218d4fbdc4e25fbec279d7fe9f65d70	ADMIN	t	\N	2026-10-21 12:46:38.691634+00	2026-10-21 12:46:38.691638+00
7968d13e-b183-4f5d-89b5-754450a3f119	lead@ai-qa.local	QA Lead	ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f	QA_LEAD	t	\N	2026-10-21 12:46:38.703193+00	2026-10-21 12:46:38.703197+00
849e703b-3303-472c-bdf9-1db19faecff1	engineer@ai-qa.local	QA Engineer	ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f	QA_ENGINEER	t	\N	2026-10-21 12:46:38.715055+00	2026-10-21 12:46:38.715059+00
\.


--
-- Data for Name: workers; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.workers (id, hostname, ip_address, status, browsers, os, max_concurrency, current_load, tags, last_heartbeat_at, registered_at) FROM stdin;
\.


--
-- Data for Name: workflow_definition_versions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.workflow_definition_versions (id, definition_id, project_id, version, state, graph, checksum, issues, created_by, created_at, published_by, published_at) FROM stdin;
\.


--
-- Data for Name: workflow_definitions; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.workflow_definitions (id, project_id, name, description, published_version, draft_version, version, created_by, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: workspaces; Type: TABLE DATA; Schema: public; Owner: aiqa
--

COPY public.workspaces (id, project_id, path, branch, status, created_at, updated_at) FROM stdin;
ws_697b442290e6	proj_391aeb3ef389	/app/runtime/workspaces/proj_391aeb3ef389	main	ACTIVE	2026-10-21 12:46:38.797327+00	2026-10-21 12:46:38.797327+00
\.


--
-- Name: agent_task_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: aiqa
--

SELECT pg_catalog.setval('public.agent_task_events_id_seq', 1, false);


--
-- Name: agent_task_artifacts agent_task_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_artifacts
    ADD CONSTRAINT agent_task_artifacts_pkey PRIMARY KEY (id);


--
-- Name: agent_task_decisions agent_task_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_decisions
    ADD CONSTRAINT agent_task_decisions_pkey PRIMARY KEY (id);


--
-- Name: agent_task_events agent_task_events_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_events
    ADD CONSTRAINT agent_task_events_pkey PRIMARY KEY (id);


--
-- Name: agent_task_evidence agent_task_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_evidence
    ADD CONSTRAINT agent_task_evidence_pkey PRIMARY KEY (id);


--
-- Name: agent_task_steps agent_task_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_steps
    ADD CONSTRAINT agent_task_steps_pkey PRIMARY KEY (id);


--
-- Name: agent_tasks agent_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_pkey PRIMARY KEY (id);


--
-- Name: ai_daily_budgets ai_daily_budgets_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.ai_daily_budgets
    ADD CONSTRAINT ai_daily_budgets_pkey PRIMARY KEY (day);


--
-- Name: ai_invocations ai_invocations_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.ai_invocations
    ADD CONSTRAINT ai_invocations_pkey PRIMARY KEY (id);


--
-- Name: ai_provider_configs ai_provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.ai_provider_configs
    ADD CONSTRAINT ai_provider_configs_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: automation_bindings automation_bindings_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.automation_bindings
    ADD CONSTRAINT automation_bindings_pkey PRIMARY KEY (id);


--
-- Name: breakpoints breakpoints_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.breakpoints
    ADD CONSTRAINT breakpoints_pkey PRIMARY KEY (id);


--
-- Name: browser_sessions browser_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.browser_sessions
    ADD CONSTRAINT browser_sessions_pkey PRIMARY KEY (id);


--
-- Name: debug_sessions debug_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.debug_sessions
    ADD CONSTRAINT debug_sessions_pkey PRIMARY KEY (id);


--
-- Name: decision_provider_configs decision_provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.decision_provider_configs
    ADD CONSTRAINT decision_provider_configs_pkey PRIMARY KEY (provider);


--
-- Name: discovery_evidence discovery_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_evidence
    ADD CONSTRAINT discovery_evidence_pkey PRIMARY KEY (id);


--
-- Name: discovery_scenarios discovery_scenarios_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_scenarios
    ADD CONSTRAINT discovery_scenarios_pkey PRIMARY KEY (id);


--
-- Name: discovery_suggestions discovery_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_suggestions
    ADD CONSTRAINT discovery_suggestions_pkey PRIMARY KEY (id);


--
-- Name: execution_jobs execution_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.execution_jobs
    ADD CONSTRAINT execution_jobs_pkey PRIMARY KEY (id);


--
-- Name: external_artifact_references external_artifact_references_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.external_artifact_references
    ADD CONSTRAINT external_artifact_references_pkey PRIMARY KEY (id);


--
-- Name: failure_analyses failure_analyses_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.failure_analyses
    ADD CONSTRAINT failure_analyses_pkey PRIMARY KEY (id);


--
-- Name: failure_records failure_records_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.failure_records
    ADD CONSTRAINT failure_records_pkey PRIMARY KEY (id);


--
-- Name: integration_audits integration_audits_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.integration_audits
    ADD CONSTRAINT integration_audits_pkey PRIMARY KEY (id);


--
-- Name: locator_history locator_history_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.locator_history
    ADD CONSTRAINT locator_history_pkey PRIMARY KEY (id);


--
-- Name: locator_repairs locator_repairs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.locator_repairs
    ADD CONSTRAINT locator_repairs_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: quality_discovery_runs quality_discovery_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.quality_discovery_runs
    ADD CONSTRAINT quality_discovery_runs_pkey PRIMARY KEY (id);


--
-- Name: releases releases_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.releases
    ADD CONSTRAINT releases_pkey PRIMARY KEY (id);


--
-- Name: requirements requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_pkey PRIMARY KEY (id);


--
-- Name: runner_profiles runner_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.runner_profiles
    ADD CONSTRAINT runner_profiles_pkey PRIMARY KEY (id);


--
-- Name: security_audits security_audits_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.security_audits
    ADD CONSTRAINT security_audits_pkey PRIMARY KEY (id);


--
-- Name: stored_artifacts stored_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.stored_artifacts
    ADD CONSTRAINT stored_artifacts_pkey PRIMARY KEY (id);


--
-- Name: team_members team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_pkey PRIMARY KEY (id);


--
-- Name: teams teams_name_key; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_name_key UNIQUE (name);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);


--
-- Name: test_cases test_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_cases
    ADD CONSTRAINT test_cases_pkey PRIMARY KEY (id);


--
-- Name: test_designs test_designs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_designs
    ADD CONSTRAINT test_designs_pkey PRIMARY KEY (id);


--
-- Name: test_executions test_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_executions
    ADD CONSTRAINT test_executions_pkey PRIMARY KEY (id);


--
-- Name: test_runs test_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_runs
    ADD CONSTRAINT test_runs_pkey PRIMARY KEY (id);


--
-- Name: breakpoints uq_breakpoint_location_source; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.breakpoints
    ADD CONSTRAINT uq_breakpoint_location_source UNIQUE (workspace_id, file_path, line_number, source);


--
-- Name: discovery_evidence uq_discovery_evidence_run_evidence; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_evidence
    ADD CONSTRAINT uq_discovery_evidence_run_evidence UNIQUE (run_id, evidence_id);


--
-- Name: discovery_scenarios uq_discovery_scenarios_run_scenario; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_scenarios
    ADD CONSTRAINT uq_discovery_scenarios_run_scenario UNIQUE (run_id, scenario_id);


--
-- Name: discovery_suggestions uq_discovery_suggestions_input; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_suggestions
    ADD CONSTRAINT uq_discovery_suggestions_input UNIQUE (run_id, scenario_id, input_hash);


--
-- Name: locator_repairs uq_locator_repairs_analysis_id; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.locator_repairs
    ADD CONSTRAINT uq_locator_repairs_analysis_id UNIQUE (analysis_id);


--
-- Name: workflow_definition_versions uq_workflow_definition_versions_definition_version; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definition_versions
    ADD CONSTRAINT uq_workflow_definition_versions_definition_version UNIQUE (definition_id, version);


--
-- Name: workflow_definitions uq_workflow_definitions_project_name; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT uq_workflow_definitions_project_name UNIQUE (project_id, name);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: workers workers_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workers
    ADD CONSTRAINT workers_pkey PRIMARY KEY (id);


--
-- Name: workflow_definition_versions workflow_definition_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definition_versions
    ADD CONSTRAINT workflow_definition_versions_pkey PRIMARY KEY (id);


--
-- Name: workflow_definitions workflow_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT workflow_definitions_pkey PRIMARY KEY (id);


--
-- Name: workspaces workspaces_pkey; Type: CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_pkey PRIMARY KEY (id);


--
-- Name: ix_agent_task_artifacts_artifact_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_artifacts_artifact_id ON public.agent_task_artifacts USING btree (artifact_id);


--
-- Name: ix_agent_task_artifacts_kind; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_artifacts_kind ON public.agent_task_artifacts USING btree (kind);


--
-- Name: ix_agent_task_artifacts_task_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_artifacts_task_id ON public.agent_task_artifacts USING btree (task_id);


--
-- Name: ix_agent_task_decisions_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_decisions_created_at ON public.agent_task_decisions USING btree (created_at);


--
-- Name: ix_agent_task_decisions_task_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_decisions_task_id ON public.agent_task_decisions USING btree (task_id);


--
-- Name: ix_agent_task_events_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_events_created_at ON public.agent_task_events USING btree (created_at);


--
-- Name: ix_agent_task_events_task_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_events_task_id ON public.agent_task_events USING btree (task_id);


--
-- Name: ix_agent_task_events_type; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_events_type ON public.agent_task_events USING btree (type);


--
-- Name: ix_agent_task_evidence_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_evidence_created_at ON public.agent_task_evidence USING btree (created_at);


--
-- Name: ix_agent_task_evidence_step_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_evidence_step_id ON public.agent_task_evidence USING btree (step_id);


--
-- Name: ix_agent_task_evidence_task_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_evidence_task_id ON public.agent_task_evidence USING btree (task_id);


--
-- Name: ix_agent_task_evidence_type; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_evidence_type ON public.agent_task_evidence USING btree (type);


--
-- Name: ix_agent_task_steps_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_steps_status ON public.agent_task_steps USING btree (status);


--
-- Name: ix_agent_task_steps_task_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_task_steps_task_id ON public.agent_task_steps USING btree (task_id);


--
-- Name: ix_agent_tasks_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_created_at ON public.agent_tasks USING btree (created_at);


--
-- Name: ix_agent_tasks_lease_expires_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_lease_expires_at ON public.agent_tasks USING btree (lease_expires_at);


--
-- Name: ix_agent_tasks_owner_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_owner_id ON public.agent_tasks USING btree (owner_id);


--
-- Name: ix_agent_tasks_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_project_id ON public.agent_tasks USING btree (project_id);


--
-- Name: ix_agent_tasks_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_status ON public.agent_tasks USING btree (status);


--
-- Name: ix_agent_tasks_type; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_type ON public.agent_tasks USING btree (type);


--
-- Name: ix_agent_tasks_workspace_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_agent_tasks_workspace_id ON public.agent_tasks USING btree (workspace_id);


--
-- Name: ix_ai_invocations_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_ai_invocations_created_at ON public.ai_invocations USING btree (created_at);


--
-- Name: ix_ai_invocations_decision_name; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_ai_invocations_decision_name ON public.ai_invocations USING btree (decision_name);


--
-- Name: ix_ai_invocations_locator_repair_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_ai_invocations_locator_repair_id ON public.ai_invocations USING btree (locator_repair_id);


--
-- Name: ix_ai_invocations_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_ai_invocations_status ON public.ai_invocations USING btree (status);


--
-- Name: ix_ai_invocations_step; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_ai_invocations_step ON public.ai_invocations USING btree (step_id);


--
-- Name: ix_ai_invocations_task; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_ai_invocations_task ON public.ai_invocations USING btree (task);


--
-- Name: ix_api_keys_key_hash; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_api_keys_key_hash ON public.api_keys USING btree (key_hash);


--
-- Name: ix_api_keys_user_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_api_keys_user_id ON public.api_keys USING btree (user_id);


--
-- Name: ix_automation_bindings_nodeid; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_automation_bindings_nodeid ON public.automation_bindings USING btree (nodeid);


--
-- Name: ix_automation_bindings_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_automation_bindings_status ON public.automation_bindings USING btree (status);


--
-- Name: ix_automation_bindings_test_case_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE UNIQUE INDEX ix_automation_bindings_test_case_id ON public.automation_bindings USING btree (test_case_id);


--
-- Name: ix_automation_bindings_workspace_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_automation_bindings_workspace_id ON public.automation_bindings USING btree (workspace_id);


--
-- Name: ix_breakpoints_workspace_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_breakpoints_workspace_id ON public.breakpoints USING btree (workspace_id);


--
-- Name: ix_browser_sessions_browser_session_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE UNIQUE INDEX ix_browser_sessions_browser_session_id ON public.browser_sessions USING btree (browser_session_id);


--
-- Name: ix_browser_sessions_case_execution_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_case_execution_id ON public.browser_sessions USING btree (case_execution_id);


--
-- Name: ix_browser_sessions_nodeid; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_nodeid ON public.browser_sessions USING btree (nodeid);


--
-- Name: ix_browser_sessions_page_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_page_id ON public.browser_sessions USING btree (page_id);


--
-- Name: ix_browser_sessions_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_run_id ON public.browser_sessions USING btree (run_id);


--
-- Name: ix_browser_sessions_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_status ON public.browser_sessions USING btree (status);


--
-- Name: ix_browser_sessions_storage_state_expires_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_storage_state_expires_at ON public.browser_sessions USING btree (storage_state_expires_at);


--
-- Name: ix_browser_sessions_worker_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_browser_sessions_worker_id ON public.browser_sessions USING btree (worker_id);


--
-- Name: ix_debug_sessions_execution_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_debug_sessions_execution_id ON public.debug_sessions USING btree (execution_id);


--
-- Name: ix_debug_sessions_failure_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_debug_sessions_failure_id ON public.debug_sessions USING btree (failure_id);


--
-- Name: ix_debug_sessions_owner_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_debug_sessions_owner_id ON public.debug_sessions USING btree (owner_id);


--
-- Name: ix_debug_sessions_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_debug_sessions_run_id ON public.debug_sessions USING btree (run_id);


--
-- Name: ix_debug_sessions_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_debug_sessions_status ON public.debug_sessions USING btree (status);


--
-- Name: ix_debug_sessions_workspace_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_debug_sessions_workspace_id ON public.debug_sessions USING btree (workspace_id);


--
-- Name: ix_discovery_evidence_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_created_at ON public.discovery_evidence USING btree (created_at);


--
-- Name: ix_discovery_evidence_kind; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_kind ON public.discovery_evidence USING btree (kind);


--
-- Name: ix_discovery_evidence_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_project_id ON public.discovery_evidence USING btree (project_id);


--
-- Name: ix_discovery_evidence_project_kind; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_project_kind ON public.discovery_evidence USING btree (project_id, kind);


--
-- Name: ix_discovery_evidence_run_dedupe; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_run_dedupe ON public.discovery_evidence USING btree (run_id, dedupe_key);


--
-- Name: ix_discovery_evidence_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_run_id ON public.discovery_evidence USING btree (run_id);


--
-- Name: ix_discovery_evidence_run_kind; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_run_kind ON public.discovery_evidence USING btree (run_id, kind);


--
-- Name: ix_discovery_evidence_state_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_evidence_state_id ON public.discovery_evidence USING btree (state_id);


--
-- Name: ix_discovery_scenarios_coverage_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_scenarios_coverage_status ON public.discovery_scenarios USING btree (coverage_status);


--
-- Name: ix_discovery_scenarios_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_scenarios_project_id ON public.discovery_scenarios USING btree (project_id);


--
-- Name: ix_discovery_scenarios_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_scenarios_run_id ON public.discovery_scenarios USING btree (run_id);


--
-- Name: ix_discovery_scenarios_run_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_scenarios_run_status ON public.discovery_scenarios USING btree (run_id, coverage_status);


--
-- Name: ix_discovery_suggestions_analysis_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_analysis_status ON public.discovery_suggestions USING btree (analysis_status);


--
-- Name: ix_discovery_suggestions_input_hash; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_input_hash ON public.discovery_suggestions USING btree (input_hash);


--
-- Name: ix_discovery_suggestions_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_project_id ON public.discovery_suggestions USING btree (project_id);


--
-- Name: ix_discovery_suggestions_review_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_review_status ON public.discovery_suggestions USING btree (review_status);


--
-- Name: ix_discovery_suggestions_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_run_id ON public.discovery_suggestions USING btree (run_id);


--
-- Name: ix_discovery_suggestions_run_review; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_run_review ON public.discovery_suggestions USING btree (run_id, review_status);


--
-- Name: ix_discovery_suggestions_run_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_run_status ON public.discovery_suggestions USING btree (run_id, analysis_status);


--
-- Name: ix_discovery_suggestions_scenario_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_discovery_suggestions_scenario_id ON public.discovery_suggestions USING btree (scenario_id);


--
-- Name: ix_execution_jobs_assigned_worker_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_execution_jobs_assigned_worker_id ON public.execution_jobs USING btree (assigned_worker_id);


--
-- Name: ix_execution_jobs_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_execution_jobs_created_at ON public.execution_jobs USING btree (created_at);


--
-- Name: ix_execution_jobs_priority; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_execution_jobs_priority ON public.execution_jobs USING btree (priority);


--
-- Name: ix_execution_jobs_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_execution_jobs_project_id ON public.execution_jobs USING btree (project_id);


--
-- Name: ix_execution_jobs_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_execution_jobs_run_id ON public.execution_jobs USING btree (run_id);


--
-- Name: ix_execution_jobs_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_execution_jobs_status ON public.execution_jobs USING btree (status);


--
-- Name: ix_external_artifact_references_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_external_artifact_references_run_id ON public.external_artifact_references USING btree (run_id);


--
-- Name: ix_failure_analyses_failure_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_failure_analyses_failure_id ON public.failure_analyses USING btree (failure_id);


--
-- Name: ix_failure_analyses_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_failure_analyses_status ON public.failure_analyses USING btree (status);


--
-- Name: ix_failure_records_classification; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_failure_records_classification ON public.failure_records USING btree (classification);


--
-- Name: ix_failure_records_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_failure_records_created_at ON public.failure_records USING btree (created_at);


--
-- Name: ix_failure_records_execution_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE UNIQUE INDEX ix_failure_records_execution_id ON public.failure_records USING btree (execution_id);


--
-- Name: ix_failure_records_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_failure_records_run_id ON public.failure_records USING btree (run_id);


--
-- Name: ix_failure_records_test_nodeid; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_failure_records_test_nodeid ON public.failure_records USING btree (test_nodeid);


--
-- Name: ix_integration_audits_action; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_integration_audits_action ON public.integration_audits USING btree (action);


--
-- Name: ix_integration_audits_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_integration_audits_created_at ON public.integration_audits USING btree (created_at);


--
-- Name: ix_integration_audits_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_integration_audits_status ON public.integration_audits USING btree (status);


--
-- Name: ix_integration_audits_system; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_integration_audits_system ON public.integration_audits USING btree (system);


--
-- Name: ix_integration_audits_target_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_integration_audits_target_id ON public.integration_audits USING btree (target_id);


--
-- Name: ix_locator_repairs_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_locator_repairs_created_at ON public.locator_repairs USING btree (created_at);


--
-- Name: ix_locator_repairs_failure_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_locator_repairs_failure_id ON public.locator_repairs USING btree (failure_id);


--
-- Name: ix_locator_repairs_state; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_locator_repairs_state ON public.locator_repairs USING btree (state);


--
-- Name: ix_locator_repairs_verification_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_locator_repairs_verification_run_id ON public.locator_repairs USING btree (verification_run_id);


--
-- Name: ix_projects_name; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_projects_name ON public.projects USING btree (name);


--
-- Name: ix_projects_owner_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_projects_owner_id ON public.projects USING btree (owner_id);


--
-- Name: ix_projects_team_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_projects_team_id ON public.projects USING btree (team_id);


--
-- Name: ix_quality_discovery_runs_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_quality_discovery_runs_created_at ON public.quality_discovery_runs USING btree (created_at);


--
-- Name: ix_quality_discovery_runs_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_quality_discovery_runs_project_id ON public.quality_discovery_runs USING btree (project_id);


--
-- Name: ix_quality_discovery_runs_requirement_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_quality_discovery_runs_requirement_id ON public.quality_discovery_runs USING btree (requirement_id);


--
-- Name: ix_quality_discovery_runs_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_quality_discovery_runs_status ON public.quality_discovery_runs USING btree (status);


--
-- Name: ix_releases_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_releases_project_id ON public.releases USING btree (project_id);


--
-- Name: ix_releases_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_releases_status ON public.releases USING btree (status);


--
-- Name: ix_releases_version; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_releases_version ON public.releases USING btree (version);


--
-- Name: ix_requirements_external_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_requirements_external_id ON public.requirements USING btree (external_id);


--
-- Name: ix_requirements_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_requirements_project_id ON public.requirements USING btree (project_id);


--
-- Name: ix_requirements_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_requirements_status ON public.requirements USING btree (status);


--
-- Name: ix_runner_profiles_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_runner_profiles_project_id ON public.runner_profiles USING btree (project_id);


--
-- Name: ix_runner_profiles_type; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_runner_profiles_type ON public.runner_profiles USING btree (type);


--
-- Name: ix_security_audits_action; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_security_audits_action ON public.security_audits USING btree (action);


--
-- Name: ix_security_audits_actor_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_security_audits_actor_id ON public.security_audits USING btree (actor_id);


--
-- Name: ix_security_audits_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_security_audits_created_at ON public.security_audits USING btree (created_at);


--
-- Name: ix_security_audits_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_security_audits_status ON public.security_audits USING btree (status);


--
-- Name: ix_security_audits_target_resource; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_security_audits_target_resource ON public.security_audits USING btree (target_resource);


--
-- Name: ix_stored_artifacts_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_stored_artifacts_project_id ON public.stored_artifacts USING btree (project_id);


--
-- Name: ix_task_event_step_cursor; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_task_event_step_cursor ON public.agent_task_events USING btree (task_id, step_id, id);


--
-- Name: ix_team_members_team_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_team_members_team_id ON public.team_members USING btree (team_id);


--
-- Name: ix_team_members_user_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_team_members_user_id ON public.team_members USING btree (user_id);


--
-- Name: ix_test_cases_automation_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_cases_automation_status ON public.test_cases USING btree (automation_status);


--
-- Name: ix_test_cases_external_case_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_cases_external_case_id ON public.test_cases USING btree (external_case_id);


--
-- Name: ix_test_cases_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_cases_project_id ON public.test_cases USING btree (project_id);


--
-- Name: ix_test_cases_requirement_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_cases_requirement_id ON public.test_cases USING btree (requirement_id);


--
-- Name: ix_test_cases_test_design_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_cases_test_design_id ON public.test_cases USING btree (test_design_id);


--
-- Name: ix_test_designs_requirement_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_designs_requirement_id ON public.test_designs USING btree (requirement_id);


--
-- Name: ix_test_executions_failure_category; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_executions_failure_category ON public.test_executions USING btree (failure_category);


--
-- Name: ix_test_executions_nodeid; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_executions_nodeid ON public.test_executions USING btree (nodeid);


--
-- Name: ix_test_executions_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_executions_run_id ON public.test_executions USING btree (run_id);


--
-- Name: ix_test_executions_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_executions_status ON public.test_executions USING btree (status);


--
-- Name: ix_test_runs_created_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_created_at ON public.test_runs USING btree (created_at);


--
-- Name: ix_test_runs_origin_failure_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_origin_failure_id ON public.test_runs USING btree (origin_failure_id);


--
-- Name: ix_test_runs_parent_run_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_parent_run_id ON public.test_runs USING btree (parent_run_id);


--
-- Name: ix_test_runs_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_project_id ON public.test_runs USING btree (project_id);


--
-- Name: ix_test_runs_runner_profile_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_runner_profile_id ON public.test_runs USING btree (runner_profile_id);


--
-- Name: ix_test_runs_runner_type; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_runner_type ON public.test_runs USING btree (runner_type);


--
-- Name: ix_test_runs_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_status ON public.test_runs USING btree (status);


--
-- Name: ix_test_runs_task_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_task_id ON public.test_runs USING btree (task_id);


--
-- Name: ix_test_runs_workspace_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_test_runs_workspace_id ON public.test_runs USING btree (workspace_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_role; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_users_role ON public.users USING btree (role);


--
-- Name: ix_workers_last_heartbeat_at; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workers_last_heartbeat_at ON public.workers USING btree (last_heartbeat_at);


--
-- Name: ix_workers_status; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workers_status ON public.workers USING btree (status);


--
-- Name: ix_workflow_definition_versions_definition_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workflow_definition_versions_definition_id ON public.workflow_definition_versions USING btree (definition_id);


--
-- Name: ix_workflow_definition_versions_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workflow_definition_versions_project_id ON public.workflow_definition_versions USING btree (project_id);


--
-- Name: ix_workflow_definition_versions_project_state; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workflow_definition_versions_project_state ON public.workflow_definition_versions USING btree (project_id, state);


--
-- Name: ix_workflow_definition_versions_state; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workflow_definition_versions_state ON public.workflow_definition_versions USING btree (state);


--
-- Name: ix_workflow_definitions_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workflow_definitions_project_id ON public.workflow_definitions USING btree (project_id);


--
-- Name: ix_workspaces_project_id; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE INDEX ix_workspaces_project_id ON public.workspaces USING btree (project_id);


--
-- Name: uq_failure_analyses_one_running_per_failure; Type: INDEX; Schema: public; Owner: aiqa
--

CREATE UNIQUE INDEX uq_failure_analyses_one_running_per_failure ON public.failure_analyses USING btree (failure_id) WHERE ((status)::text = 'RUNNING'::text);


--
-- Name: agent_task_artifacts agent_task_artifacts_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_artifacts
    ADD CONSTRAINT agent_task_artifacts_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES public.stored_artifacts(id) ON DELETE CASCADE;


--
-- Name: agent_task_artifacts agent_task_artifacts_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_artifacts
    ADD CONSTRAINT agent_task_artifacts_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.agent_task_steps(id) ON DELETE SET NULL;


--
-- Name: agent_task_artifacts agent_task_artifacts_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_artifacts
    ADD CONSTRAINT agent_task_artifacts_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id) ON DELETE CASCADE;


--
-- Name: agent_task_decisions agent_task_decisions_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_decisions
    ADD CONSTRAINT agent_task_decisions_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.agent_task_steps(id) ON DELETE SET NULL;


--
-- Name: agent_task_decisions agent_task_decisions_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_decisions
    ADD CONSTRAINT agent_task_decisions_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id) ON DELETE CASCADE;


--
-- Name: agent_task_events agent_task_events_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_events
    ADD CONSTRAINT agent_task_events_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id) ON DELETE CASCADE;


--
-- Name: agent_task_evidence agent_task_evidence_artifact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_evidence
    ADD CONSTRAINT agent_task_evidence_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES public.stored_artifacts(id) ON DELETE SET NULL;


--
-- Name: agent_task_evidence agent_task_evidence_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_evidence
    ADD CONSTRAINT agent_task_evidence_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.agent_task_steps(id) ON DELETE SET NULL;


--
-- Name: agent_task_evidence agent_task_evidence_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_evidence
    ADD CONSTRAINT agent_task_evidence_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id) ON DELETE CASCADE;


--
-- Name: agent_task_steps agent_task_steps_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_task_steps
    ADD CONSTRAINT agent_task_steps_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id) ON DELETE CASCADE;


--
-- Name: agent_tasks agent_tasks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.agent_tasks
    ADD CONSTRAINT agent_tasks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: automation_bindings automation_bindings_test_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.automation_bindings
    ADD CONSTRAINT automation_bindings_test_case_id_fkey FOREIGN KEY (test_case_id) REFERENCES public.test_cases(id) ON DELETE CASCADE;


--
-- Name: breakpoints breakpoints_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.breakpoints
    ADD CONSTRAINT breakpoints_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE SET NULL;


--
-- Name: browser_sessions browser_sessions_case_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.browser_sessions
    ADD CONSTRAINT browser_sessions_case_execution_id_fkey FOREIGN KEY (case_execution_id) REFERENCES public.test_executions(id) ON DELETE SET NULL;


--
-- Name: browser_sessions browser_sessions_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.browser_sessions
    ADD CONSTRAINT browser_sessions_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE CASCADE;


--
-- Name: debug_sessions debug_sessions_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.debug_sessions
    ADD CONSTRAINT debug_sessions_execution_id_fkey FOREIGN KEY (execution_id) REFERENCES public.test_executions(id) ON DELETE SET NULL;


--
-- Name: debug_sessions debug_sessions_failure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.debug_sessions
    ADD CONSTRAINT debug_sessions_failure_id_fkey FOREIGN KEY (failure_id) REFERENCES public.failure_records(id) ON DELETE SET NULL;


--
-- Name: debug_sessions debug_sessions_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.debug_sessions
    ADD CONSTRAINT debug_sessions_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE SET NULL;


--
-- Name: discovery_evidence discovery_evidence_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_evidence
    ADD CONSTRAINT discovery_evidence_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: discovery_evidence discovery_evidence_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_evidence
    ADD CONSTRAINT discovery_evidence_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.quality_discovery_runs(id) ON DELETE CASCADE;


--
-- Name: discovery_scenarios discovery_scenarios_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_scenarios
    ADD CONSTRAINT discovery_scenarios_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: discovery_scenarios discovery_scenarios_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_scenarios
    ADD CONSTRAINT discovery_scenarios_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.quality_discovery_runs(id) ON DELETE CASCADE;


--
-- Name: discovery_suggestions discovery_suggestions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_suggestions
    ADD CONSTRAINT discovery_suggestions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: discovery_suggestions discovery_suggestions_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.discovery_suggestions
    ADD CONSTRAINT discovery_suggestions_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.quality_discovery_runs(id) ON DELETE CASCADE;


--
-- Name: execution_jobs execution_jobs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.execution_jobs
    ADD CONSTRAINT execution_jobs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: execution_jobs execution_jobs_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.execution_jobs
    ADD CONSTRAINT execution_jobs_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE CASCADE;


--
-- Name: external_artifact_references external_artifact_references_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.external_artifact_references
    ADD CONSTRAINT external_artifact_references_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE CASCADE;


--
-- Name: failure_analyses failure_analyses_failure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.failure_analyses
    ADD CONSTRAINT failure_analyses_failure_id_fkey FOREIGN KEY (failure_id) REFERENCES public.failure_records(id) ON DELETE CASCADE;


--
-- Name: failure_records failure_records_execution_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.failure_records
    ADD CONSTRAINT failure_records_execution_id_fkey FOREIGN KEY (execution_id) REFERENCES public.test_executions(id) ON DELETE CASCADE;


--
-- Name: failure_records failure_records_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.failure_records
    ADD CONSTRAINT failure_records_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE CASCADE;


--
-- Name: ai_invocations fk_ai_invocations_locator_repair_id_locator_repairs; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.ai_invocations
    ADD CONSTRAINT fk_ai_invocations_locator_repair_id_locator_repairs FOREIGN KEY (locator_repair_id) REFERENCES public.locator_repairs(id) ON DELETE SET NULL;


--
-- Name: projects fk_projects_owner_id; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_owner_id FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: projects fk_projects_team_id; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT fk_projects_team_id FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: stored_artifacts fk_stored_artifacts_project_id; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.stored_artifacts
    ADD CONSTRAINT fk_stored_artifacts_project_id FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE SET NULL;


--
-- Name: test_runs fk_test_runs_origin_failure_id; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_runs
    ADD CONSTRAINT fk_test_runs_origin_failure_id FOREIGN KEY (origin_failure_id) REFERENCES public.failure_records(id) ON DELETE SET NULL;


--
-- Name: test_runs fk_test_runs_parent_run_id; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_runs
    ADD CONSTRAINT fk_test_runs_parent_run_id FOREIGN KEY (parent_run_id) REFERENCES public.test_runs(id) ON DELETE SET NULL;


--
-- Name: test_runs fk_test_runs_task_id; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_runs
    ADD CONSTRAINT fk_test_runs_task_id FOREIGN KEY (task_id) REFERENCES public.agent_tasks(id) ON DELETE SET NULL;


--
-- Name: locator_repairs locator_repairs_analysis_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.locator_repairs
    ADD CONSTRAINT locator_repairs_analysis_id_fkey FOREIGN KEY (analysis_id) REFERENCES public.failure_analyses(id) ON DELETE CASCADE;


--
-- Name: locator_repairs locator_repairs_failure_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.locator_repairs
    ADD CONSTRAINT locator_repairs_failure_id_fkey FOREIGN KEY (failure_id) REFERENCES public.failure_records(id) ON DELETE CASCADE;


--
-- Name: locator_repairs locator_repairs_verification_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.locator_repairs
    ADD CONSTRAINT locator_repairs_verification_run_id_fkey FOREIGN KEY (verification_run_id) REFERENCES public.test_runs(id) ON DELETE SET NULL;


--
-- Name: quality_discovery_runs quality_discovery_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.quality_discovery_runs
    ADD CONSTRAINT quality_discovery_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: quality_discovery_runs quality_discovery_runs_requirement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.quality_discovery_runs
    ADD CONSTRAINT quality_discovery_runs_requirement_id_fkey FOREIGN KEY (requirement_id) REFERENCES public.requirements(id) ON DELETE SET NULL;


--
-- Name: releases releases_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.releases
    ADD CONSTRAINT releases_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: requirements requirements_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.requirements
    ADD CONSTRAINT requirements_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: runner_profiles runner_profiles_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.runner_profiles
    ADD CONSTRAINT runner_profiles_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: team_members team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: team_members team_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: test_cases test_cases_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_cases
    ADD CONSTRAINT test_cases_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: test_cases test_cases_requirement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_cases
    ADD CONSTRAINT test_cases_requirement_id_fkey FOREIGN KEY (requirement_id) REFERENCES public.requirements(id) ON DELETE SET NULL;


--
-- Name: test_cases test_cases_test_design_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_cases
    ADD CONSTRAINT test_cases_test_design_id_fkey FOREIGN KEY (test_design_id) REFERENCES public.test_designs(id) ON DELETE SET NULL;


--
-- Name: test_designs test_designs_requirement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_designs
    ADD CONSTRAINT test_designs_requirement_id_fkey FOREIGN KEY (requirement_id) REFERENCES public.requirements(id) ON DELETE CASCADE;


--
-- Name: test_executions test_executions_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_executions
    ADD CONSTRAINT test_executions_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.test_runs(id) ON DELETE CASCADE;


--
-- Name: test_runs test_runs_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.test_runs
    ADD CONSTRAINT test_runs_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: workflow_definition_versions workflow_definition_versions_definition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definition_versions
    ADD CONSTRAINT workflow_definition_versions_definition_id_fkey FOREIGN KEY (definition_id) REFERENCES public.workflow_definitions(id) ON DELETE CASCADE;


--
-- Name: workflow_definition_versions workflow_definition_versions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definition_versions
    ADD CONSTRAINT workflow_definition_versions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: workflow_definitions workflow_definitions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workflow_definitions
    ADD CONSTRAINT workflow_definitions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- Name: workspaces workspaces_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: aiqa
--

ALTER TABLE ONLY public.workspaces
    ADD CONSTRAINT workspaces_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict 3x1RcwOSkDssnTYxtfFPhJhJ47W9J2ylVaYymdnbx0IHR4Ojpnr17r5pk2SflxF

