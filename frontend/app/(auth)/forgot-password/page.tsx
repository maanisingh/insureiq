"use client";

import { useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "sonner";
import { Loader2, Copy, Check } from "lucide-react";
import { api } from "@/lib/api";

const schema = z.object({ email: z.string().email("Enter a valid email") });
type FormData = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [loading, setLoading] = useState(false);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [copied, setCopied]         = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    try {
      const res: any = await api.auth.forgotPassword(data.email);
      if (res?.reset_token) setResetToken(res.reset_token);
      toast.success("Reset token generated");
    } catch {
      // Always show success to avoid email enumeration
      toast.success("If that email exists, a reset link has been issued.");
    } finally {
      setLoading(false);
    }
  };

  const copyToken = () => {
    if (!resetToken) return;
    navigator.clipboard.writeText(resetToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reset password</CardTitle>
        <CardDescription>Enter your email to receive a reset token</CardDescription>
      </CardHeader>
      {!resetToken ? (
        <form onSubmit={handleSubmit(onSubmit)}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" placeholder="you@company.com" {...register("email")} />
              {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
            </div>
          </CardContent>
          <CardFooter className="flex-col gap-3">
            <Button type="submit" className="w-full" disabled={loading}>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Send reset token
            </Button>
            <Link href="/login" className="text-sm text-muted-foreground hover:text-foreground">
              ← Back to sign in
            </Link>
          </CardFooter>
        </form>
      ) : (
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Copy this token and use it to reset your password. It expires in 1 hour.
          </p>
          <div className="flex items-center gap-2 p-3 rounded-lg bg-muted font-mono text-xs break-all">
            <span className="flex-1">{resetToken}</span>
            <Button size="icon" variant="ghost" onClick={copyToken}>
              {copied ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
          <Link href={`/reset-password?token=${resetToken}`}>
            <Button className="w-full">Use token to reset password →</Button>
          </Link>
        </CardContent>
      )}
    </Card>
  );
}
