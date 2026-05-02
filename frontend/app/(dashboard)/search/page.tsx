import { redirect } from "next/navigation";

// Semantic search is now embedded in the Chat page.
export default function SearchPage() {
  redirect("/chat");
}
