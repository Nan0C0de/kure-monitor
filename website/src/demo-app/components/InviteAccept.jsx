import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Server, UserPlus, AlertCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { api } from '../services/api';

const MIN_PASSWORD_LENGTH = 8;
const USERNAME_MIN = 3;
const USERNAME_MAX = 64;

const InviteAccept = () => {
  const { token } = useParams();
  const navigate = useNavigate();
  const { acceptInvitation } = useAuth();

  const [loadingInvite, setLoadingInvite] = useState(true);
  const [invite, setInvite] = useState(null); // { role, expires_at }
  const [loadError, setLoadError] = useState(null); // { title, message }

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [email, setEmail] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [isDark] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('kure-theme') === 'dark';
    }
    return false;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingInvite(true);
      setLoadError(null);
      try {
        const data = await api.getInvitation(token);
        if (!cancelled) {
          setInvite(data);
        }
      } catch (err) {
        if (cancelled) return;
        if (err?.status === 404) {
          setLoadError({
            title: 'Invitation not found',
            message: 'This invitation link is invalid.',
          });
        } else if (err?.status === 410) {
          setLoadError({
            title: 'Invitation unavailable',
            message: 'This invitation has expired or has already been used.',
          });
        } else {
          setLoadError({
            title: 'Unable to load invitation',
            message: err?.message || 'Please try again later.',
          });
        }
      } finally {
        if (!cancelled) setLoadingInvite(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const validate = () => {
    if (username.trim().length < USERNAME_MIN || username.trim().length > USERNAME_MAX) {
      return `Username must be between ${USERNAME_MIN} and ${USERNAME_MAX} characters`;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`;
    }
    if (password !== repeatPassword) {
      return 'Passwords do not match';
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const validationError = validate();
    if (validationError) {
      setSubmitError(validationError);
      return;
    }

    setSubmitting(true);
    setSubmitError('');
    try {
      await acceptInvitation({
        token,
        username: username.trim(),
        password,
        email: email.trim() || undefined,
      });
      navigate('/', { replace: true });
    } catch (err) {
      if (err?.status === 410) {
        setSubmitError('This invitation has expired or has already been used.');
      } else if (err?.status === 404) {
        setSubmitError('Invitation not found.');
      } else if (err?.status === 409) {
        setSubmitError(err?.message || 'That username is already taken.');
      } else {
        setSubmitError(err?.message || 'Unable to accept invitation.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = `w-full px-4 py-3 rounded-md border text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
    isDark
      ? 'bg-gray-700 border-gray-600 text-gray-200 placeholder-gray-500'
      : 'bg-white border-gray-300 text-gray-900 placeholder-gray-400'
  }`;
  const labelCls = `block text-sm font-medium mb-2 ${isDark ? 'text-gray-300' : 'text-gray-700'}`;

  const formatExpiry = (iso) => {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  return (
    <div className={`min-h-screen flex items-center justify-center ${isDark ? 'bg-gray-900' : 'bg-gray-100'}`}>
      <div className={`w-full max-w-md p-8 rounded-lg shadow-lg ${isDark ? 'bg-gray-800' : 'bg-white'}`}>
        <div className="flex flex-col items-center mb-6">
          <Server className={`w-12 h-12 mb-3 ${isDark ? 'text-blue-400' : 'text-blue-500'}`} />
          <h1 className={`text-2xl font-bold ${isDark ? 'text-gray-100' : 'text-gray-900'}`}>
            Accept Invitation
          </h1>
        </div>

        {loadingInvite && (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <span className={`ml-2 text-sm ${isDark ? 'text-gray-300' : 'text-gray-600'}`}>
              Checking invitation...
            </span>
          </div>
        )}

        {!loadingInvite && loadError && (
          <div
            role="alert"
            className={`rounded-md p-4 flex items-start gap-3 ${
              isDark ? 'bg-red-900/40 text-red-200' : 'bg-red-50 text-red-800'
            }`}
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">{loadError.title}</p>
              <p className="text-sm mt-1">{loadError.message}</p>
              <button
                onClick={() => navigate('/login')}
                className={`mt-3 text-sm underline ${isDark ? 'text-red-100' : 'text-red-700'}`}
              >
                Go to sign in
              </button>
            </div>
          </div>
        )}

        {!loadingInvite && !loadError && invite && (
          <>
            <div
              className={`mb-6 rounded-md px-4 py-3 text-sm ${
                isDark ? 'bg-blue-900/30 text-blue-200' : 'bg-blue-50 text-blue-800'
              }`}
            >
              <p>
                You have been invited as a <strong>{invite.role}</strong> user.
              </p>
              {invite.expires_at && (
                <p className={`mt-1 text-xs ${isDark ? 'text-blue-300' : 'text-blue-700'}`}>
                  Expires: {formatExpiry(invite.expires_at)}
                </p>
              )}
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label htmlFor="invite-role" className={labelCls}>Role</label>
                <input
                  id="invite-role"
                  type="text"
                  value={invite.role}
                  readOnly
                  className={`${inputCls} cursor-not-allowed opacity-70`}
                />
              </div>

              <div>
                <label htmlFor="invite-username" className={labelCls}>Username</label>
                <input
                  id="invite-username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="3–64 characters"
                  autoComplete="username"
                  autoFocus
                  className={inputCls}
                />
              </div>

              <div>
                <label htmlFor="invite-password" className={labelCls}>Password</label>
                <input
                  id="invite-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                  className={inputCls}
                />
              </div>

              <div>
                <label htmlFor="invite-repeat-password" className={labelCls}>Repeat password</label>
                <input
                  id="invite-repeat-password"
                  type="password"
                  value={repeatPassword}
                  onChange={(e) => setRepeatPassword(e.target.value)}
                  placeholder="Repeat password"
                  autoComplete="new-password"
                  className={inputCls}
                />
              </div>

              <div>
                <label htmlFor="invite-email" className={labelCls}>Email (optional)</label>
                <input
                  id="invite-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  className={inputCls}
                />
              </div>

              {submitError && (
                <div
                  role="alert"
                  className={`text-sm p-3 rounded-md ${isDark ? 'bg-red-900/50 text-red-300' : 'bg-red-50 text-red-700'}`}
                >
                  {submitError}
                </div>
              )}

              <button
                type="submit"
                disabled={submitting}
                className={`w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-md text-sm font-medium text-white transition-colors ${
                  submitting ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
                }`}
              >
                {submitting ? (
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <>
                    <UserPlus className="w-4 h-4" />
                    <span>Create account</span>
                  </>
                )}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
};

export default InviteAccept;
