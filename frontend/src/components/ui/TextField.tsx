import { useId, useState } from 'react'
import type { InputHTMLAttributes } from 'react'

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  label: string
  error?: string
  hint?: string
}

function IconEye() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M1 7s2.2-4 6-4 6 4 6 4-2.2 4-6 4-6-4-6-4Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="7" cy="7" r="1.6" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  )
}

function IconEyeOff() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path
        d="M1.5 1.5l11 11M2 7s2.2 4 6 4c1 0 1.9-.24 2.7-.6M6 3.2C6.32 3.07 6.65 3 7 3c3.8 0 6 4 6 4-.3.53-.75 1.15-1.33 1.75"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function TextField({ label, error, hint, className, type, ...inputProps }: TextFieldProps) {
  const id = useId()
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  const [mostrarPassword, setMostrarPassword] = useState(false)
  const esPassword = type === 'password'

  const inputClassName = [
    'field__input',
    error && 'field__input--error',
    esPassword && 'field__input--con-icono',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={className ? `field ${className}` : 'field'}>
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      <div className="field__control">
        <input
          id={id}
          type={esPassword ? (mostrarPassword ? 'text' : 'password') : type}
          className={inputClassName}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...inputProps}
        />
        {esPassword && (
          <button
            type="button"
            className="field__toggle"
            data-autofocus-skip
            aria-label={mostrarPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
            onClick={() => setMostrarPassword((v) => !v)}
          >
            {mostrarPassword ? <IconEyeOff /> : <IconEye />}
          </button>
        )}
      </div>
      {error ? (
        <p id={`${id}-error`} className="field__error">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
