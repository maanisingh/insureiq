import { auth } from "@/auth";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  const session = await auth();
  const { pathname } = request.nextUrl;

  const isAuth  = !!session;
  const isPublic = ["/", "/login", "/register", "/forgot-password", "/reset-password"].some(
    (p) => pathname === p || pathname.startsWith(p + "?"),
  );

  if (!isAuth && !isPublic) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (isAuth && ["/login", "/register"].includes(pathname)) {
    return NextResponse.redirect(new URL("/chat", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
