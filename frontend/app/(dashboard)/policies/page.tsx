import { redirect } from "next/navigation";

// Policies are now managed through the Documents page (AI-generated docs).
// The /policies API routes still exist and are used by the PolicyAgent internally.
export default function PoliciesPage() {
  redirect("/documents");
}
