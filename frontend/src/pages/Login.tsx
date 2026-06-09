import { Boxes, Loader2 } from "lucide-react"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { useAuth } from "@/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function Login() {
  const { requestCode, verifyCode } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState<"email" | "code">("email")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onRequest = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await requestCode(email)
      setStep("code")
    } catch {
      setError("Impossible d'envoyer le code. Réessayez.")
    } finally {
      setBusy(false)
    }
  }

  const onVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await verifyCode(email, code)
      navigate("/", { replace: true })
    } catch {
      setError("Code invalide ou expiré.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-svh grid place-items-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground">
            <Boxes className="size-6" />
          </div>
          <CardTitle className="text-xl">Matières premières</CardTitle>
          <CardDescription>
            {step === "email"
              ? "Saisissez votre email pour recevoir un code de connexion."
              : `Entrez le code envoyé à ${email}.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {step === "email" ? (
            <form onSubmit={onRequest} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  autoFocus
                  placeholder="vous@exemple.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy && <Loader2 className="animate-spin" />} Recevoir un code
              </Button>
            </form>
          ) : (
            <form onSubmit={onVerify} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="code">Code à 6 chiffres</Label>
                <Input
                  id="code"
                  inputMode="numeric"
                  required
                  autoFocus
                  placeholder="123456"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className="text-center text-lg tracking-[0.4em]"
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy && <Loader2 className="animate-spin" />} Se connecter
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setStep("email")
                  setCode("")
                  setError(null)
                }}
              >
                Changer d'email
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
