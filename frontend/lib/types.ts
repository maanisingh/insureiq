// TypeScript types mirroring backend Pydantic schemas

export interface TokenResponse {
  access_token: string;
  token_type:   string;
  user_id:      string;
  email:        string;
  full_name?:   string;
}

export interface UserResponse {
  id:          string;
  email:       string;
  full_name?:  string;
  is_active:   boolean;
  is_verified: boolean;
}

export interface Workspace {
  id:          string;
  name:        string;
  description?: string;
  created_at:  string;
}

export interface Policy {
  id:            string;
  policy_number: string;
  policy_type?:  string;
  policy_data?:  Record<string, unknown>;
  status?:       string;
  created_at?:   string;
  updated_at?:   string;
}

export interface UploadResponse {
  id:                string;
  workspace_id:      string;
  filename:          string;
  original_filename?: string;
  file_type:         string;
  file_size:         number;
  extraction_status: "pending" | "processing" | "done" | "failed";
  chunk_count:       number;
  uploaded_at:       string;
  indexed_at?:       string;
}

export interface UploadListItem {
  id:                string;
  filename:          string;
  original_filename?: string;
  file_type:         string;
  file_size:         number;
  extraction_status: string;
  chunk_count:       number;
  uploaded_at:       string;
}

export interface ChatSource {
  id?:    string;
  score?: number;
  text:   string;
  source?: string;
  layer:  "global" | "workspace";
  tool?:  string;
  agent?: string;
}

export interface ChatMessage {
  id:      string;
  role:    "user" | "assistant";
  content: string;
  agent?:  string;
}

export interface ChatSession {
  session_id:    string;
  created_at:    string;
  message_count: number;
  first_message?: string;
}

// ── Generated Documents ───────────────────────────────────────────────────────

export type GeneratedDocType = "policy_document" | "underwriting_memo";

export interface GeneratedDocSummary {
  id:         string;
  title:      string;
  doc_type:   GeneratedDocType;
  word_count: number;
  indexed_at: string | null;  // null = still indexing into RAG
  created_at: string;
}

export interface GeneratedDoc extends GeneratedDocSummary {
  content:  string;
  metadata: Record<string, unknown>;
}

export interface SearchResult {
  id?:     string;
  score?:  number;
  text:    string;
  source?: string;
  type?:   string;
  layer?:  "global" | "workspace";
}

export interface ApiKey {
  id:           string;
  name:         string;
  key_prefix:   string;
  is_active:    boolean;
  created_at:   string;
  last_used_at?: string;
}

export interface ApiKeyCreated extends ApiKey {
  raw_key: string;
}

export type AgentName =
  | "RAGAgent"
  | "ResearchAgent"
  | "PricingAgent"
  | "PolicyAgent"
  | "UnderwritingAgent";

export interface SSEEvent {
  type:       "routing" | "tool_call" | "tool_result" | "token" | "done" | "error";
  agent?:     string;
  tool?:      string;
  preview?:   string;
  content?:   string;
  sources?:   ChatSource[];
  agent_used?: string;
  session_id?: string;
  message?:   string;
}
