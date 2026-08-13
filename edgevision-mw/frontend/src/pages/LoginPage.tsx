import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Shield, Eye, EyeOff } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { Button, FormField, Input, ProgressBar } from "../components/ui";

type PasswordStrength = "weak" | "fair" | "good" | "empty";

function getPasswordStrength(password: string): PasswordStrength {
  if (!password) return "empty";
  const hasLower = /[a-z]/.test(password);
  const hasUpper = /[A-Z]/.test(password);
  const hasDigit = /\d/.test(password);
  const longEnough = password.length >= 8;
  if (longEnough && hasLower && hasUpper && hasDigit) return "good";
  if (password.length >= 8 && (hasLower || hasUpper) && hasDigit) return "fair";
  return "weak";
}

const STRENGTH_PROGRESS: Record<PasswordStrength, number> = {
  empty: 0,
  weak: 25,
  fair: 60,
  good: 100,
};

export default function LoginPage() {
  const { login, register } = useAuth();
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fullName, setFullName] = useState("");
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const passwordStrength = isRegister ? getPasswordStrength(password) : "empty";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isRegister) {
        await register(email, password, fullName);
      } else {
        await login(email, password);
      }
    } catch {
      setError(t("login.authFailed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-root login-root--trust">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo" aria-hidden>
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <p className="login-eyebrow">{t("login.eyebrow")}</p>
          <h1>{t("login.title")}</h1>
          <p className="login-subtitle">{t("login.valueStatement")}</p>
        </div>

        <div className="login-trust-block" role="note">
          <Shield size={16} aria-hidden />
          <div>
            <p>{t("login.trustPrivacy")}</p>
            <p className="login-trust-secondary">{t("login.trustConsent")}</p>
            <p className="login-trust-secondary">{t("login.trustJurisdiction")}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          {isRegister && (
            <>
              <FormField label={t("login.fullName")} htmlFor="login-fullname">
                <Input
                  id="login-fullname"
                  type="text"
                  placeholder="John Mwangi"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                />
              </FormField>
              <p className="login-role-note">{t("login.defaultRoleNote")}</p>
            </>
          )}

          <FormField label={t("login.email")} htmlFor="login-email">
            <Input
              id="login-email"
              type="email"
              placeholder="admin@edgevision.mw"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </FormField>

          <FormField label={t("login.password")} htmlFor="login-password">
            <div className="login-password-row">
              <Input
                id="login-password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={isRegister ? 8 : undefined}
                autoComplete={isRegister ? "new-password" : "current-password"}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="login-password-toggle"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </Button>
            </div>
            {isRegister && passwordStrength !== "empty" && (
              <div className="login-strength">
                <ProgressBar value={STRENGTH_PROGRESS[passwordStrength]} />
                <p className={`login-password-strength strength-${passwordStrength}`}>
                  {t(`login.passwordStrength.${passwordStrength}`)}
                </p>
              </div>
            )}
            {isRegister && <p className="login-password-hint">{t("login.passwordHint")}</p>}
          </FormField>

          <Button type="submit" variant="primary" className="login-btn" loading={loading} disabled={loading}>
            {isRegister ? t("login.createAccount") : t("login.signIn")}
          </Button>
        </form>

        <div className="login-footer">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
              setShowPassword(false);
            }}
            className="login-toggle"
          >
            {isRegister ? t("login.hasAccount") : t("login.noAccount")}
          </Button>
        </div>
      </div>

      <div className="login-bg-pattern" aria-hidden />
    </div>
  );
}
