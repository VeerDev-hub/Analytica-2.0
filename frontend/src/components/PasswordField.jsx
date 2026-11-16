import { useState } from 'react';
import { Field, Input } from './ui.jsx';
import { Icon } from './icons.jsx';
import { SCORE_LABELS, passwordProblems, passwordScore } from '../lib/password.js';

const TONE = ['bg-border', 'bg-danger', 'bg-warn', 'bg-ok', 'bg-ok'];

/**
 * Password input with a show/hide toggle and a strength meter that applies the server's rules.
 * @param {{label?: string, value: string, onChange: (v: string) => void, email?: string, name?: string,
 *   autoComplete?: string, required?: boolean, id?: string}} props
 */
export function PasswordField({ label = 'Password', value, onChange, email, name, autoComplete = 'new-password', required = true }) {
  const [show, setShow] = useState(false);
  const problems = value ? passwordProblems(value, { email, name }) : [];
  const score = value ? passwordScore(value, { email, name }) : 0;
  return (
    <Field label={label}>
      {(id) => (
        <div>
          <div className="relative">
            <Input
              id={id}
              type={show ? 'text' : 'password'}
              required={required}
              minLength={8}
              maxLength={128}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              autoComplete={autoComplete}
              className="pr-10"
              aria-describedby={`${id}-hint`}
            />
            <button
              type="button"
              onClick={() => setShow(!show)}
              className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted hover:text-fg"
              aria-label={show ? 'Hide password' : 'Show password'}
            >
              <Icon name={show ? 'eyeOff' : 'eye'} size={16} />
            </button>
          </div>
          <div className="mt-2 grid grid-cols-4 gap-1" aria-hidden>
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className={`h-1 rounded-full ${value && i <= Math.max(score, 1) ? TONE[score] : 'bg-border'}`} />
            ))}
          </div>
          <p id={`${id}-hint`} className={`mt-1.5 text-xs ${problems.length ? 'text-danger' : 'text-muted'}`}>
            {!value ? 'At least 8 characters. Longer is better; mix letters, numbers and symbols.' : problems.length ? problems[0] : SCORE_LABELS[score]}
          </p>
        </div>
      )}
    </Field>
  );
}
