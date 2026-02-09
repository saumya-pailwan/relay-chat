import { useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Login({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const endpoint = isRegister ? "auth/register" : "auth/login";
      const payload = isRegister
        ? { email, username, password }
        : { email, password };

      const response = await axios.post(`${API}/${endpoint}`, payload);
      const { access_token, user } = response.data;

      toast.success(isRegister ? "Account created!" : "Welcome back!");
      onLogin(access_token, user);
    } catch (error) {
      const message =
        error.response?.data?.detail || "Authentication failed";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <div className="logo-container">
            <div className="logo-icon">💬</div>
            <h1 className="logo-text">RelayChat</h1>
          </div>
          <p className="subtitle">Scalable real-time messaging</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              data-testid="email-input"
            />
          </div>

          {isRegister && (
            <div className="form-group">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="johndoe"
                required
                data-testid="username-input"
              />
            </div>
          )}

          <div className="form-group">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              data-testid="password-input"
            />
          </div>

          <Button
            type="submit"
            className="submit-button"
            disabled={loading}
            data-testid="submit-button"
          >
            {loading ? "Please wait..." : isRegister ? "Create Account" : "Sign In"}
          </Button>
        </form>

        <div className="toggle-mode">
          <span>{isRegister ? "Already have an account?" : "Don't have an account?"}</span>
          <button
            type="button"
            onClick={() => setIsRegister(!isRegister)}
            className="toggle-link"
            data-testid="toggle-auth-mode"
          >
            {isRegister ? "Sign In" : "Create Account"}
          </button>
        </div>
      </div>
    </div>
  );
}
