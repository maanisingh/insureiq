"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Suspense } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";

const schema = z.object({
  token:        z.string().min(1, "Token required"),
  new_password: z.string().min(8, "Password must be at least 8 characters"),
  confirm:      z.string(),
}).refine((d) => d.new_password === d.confirm, { message: "Passwords do not match", path: ["confirm"] });
type FormData = z.infer<typeof schema>;

function ResetForm() {
  const router       = useRouter();
  const searchParams = useSearchParams();
  const tokenFromUrl = searchParams.get("token") ?? "";
  const [loading, setLoading] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver:      zodResolver(schema),
    defaultValues: { token: tokenFromUrl },
  });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    try {
      await api.auth.resetPassword({ token: data.token, new_password: data.new_password });
      toast.success("Password reset successfully. Please sign in.");
      router.push("/login");
    } catch (e: any) {
      toast.error(e.message ?? "Reset failed — token may be expired or already used.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set new password</CardTitle>
        <CardDescription>Enter your reset token and choose a new password</CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit(onSubmit)}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="token">Reset token</Label>
            <Input id="token" placeholder="Paste reset token here" {...register("token")} />
            {errors.token && <p className="text-xs text-destructive">{errors.token.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="new_password">New password</Label>
            <Input id="new_password" type="password" placeholder="8+ characters" {...register("new_password")} />
            {errors.new_password && <p className="text-xs text-destructive">{errors.new_password.message}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm">Confirm new password</Label>
            <Input id="confirm" type="password" {...register("confirm")} />
            {errors.confirm && <p className="text-xs text-destructive">{errors.confirm.message}</p>}
          </div>
        </CardContent>
        <CardFooter className="flex-col gap-3">
          <Button type="submit" className="w-full" disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Reset password
          </Button>
          <Link href="/login" className="text-sm text-muted-foreground hover:text-foreground">
            ← Back to sign in
          </Link>
        </CardFooter>
      </form>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="text-center text-muted-foreground">Loading…</div>}>
      <ResetForm />
    </Suspense>
  );
}
