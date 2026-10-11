"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowUpRight,
  LockKeyhole,
  MoveUpRight,
} from "lucide-react";
import { Brand } from "./ui";

export function AuthFrame({
  children,
  role = "candidate",
  inbox = false,
}: {
  children: ReactNode;
  role?: "candidate" | "employer";
  inbox?: boolean;
}) {
  return (
    <div className={`vector-auth${inbox ? " vector-auth-inbox" : ""}`}>
      <div className="vector-auth-frame">
        <div className="vector-auth-form-side">
          <header className="vector-auth-brand">
            <Brand />
            <Link className="vector-auth-home" href="/">
              <ArrowLeft size={16} aria-hidden="true" /> На главную
            </Link>
          </header>
          <main className="vector-auth-main">{children}</main>
          <footer className="vector-auth-footer">
            <LockKeyhole size={16} aria-hidden="true" />
            <span>Доступ к контактам — по отдельному согласию.</span>
          </footer>
        </div>
        <AuthVisual role={role} />
      </div>
    </div>
  );
}

function AuthVisual({ role }: { role: "candidate" | "employer" }) {
  return (
    <aside className="vector-auth-aside" aria-label="Возможности ФСП Вектор">
      <div className="vector-auth-story">
        <h2>
          Твой опыт.
          <br />
          Твои возможности.
        </h2>
        <p>
          {role === "employer"
            ? "Познакомься со специалистом через его навыки и основания каждого результата."
            : "Собери навыки, результаты и достижения в одном профессиональном профиле."}
        </p>
      </div>
      <figure className="vector-auth-art">
        <div className="vector-auth-ribbon" aria-hidden="true">
          <img
            src="/assets/vector-ribbon.png"
            alt=""
            width={1536}
            height={1024}
            loading="eager"
            decoding="async"
            className="vector-auth-ribbon-image"
          />
        </div>
        <div className="vector-auth-credential" aria-hidden="true">
          <div className="vector-auth-credential-header">
            <span className="vector-auth-credential-label">
              Пример паспорта
            </span>
            <MoveUpRight size={22} />
          </div>
          <div className="vector-auth-credential-identity">
            <span className="vector-auth-monogram">В</span>
            <div>
              <strong>Твой профессиональный профиль</strong>
              <span>Паспорт компетенций</span>
            </div>
          </div>
          <div className="vector-auth-credential-content">
            <div>
              <span>Навыки и источники</span>
              <ArrowUpRight size={18} />
            </div>
            <div>
              <span>Достижения и история</span>
              <ArrowUpRight size={18} />
            </div>
            <div>
              <span>Управление доступом</span>
              <LockKeyhole size={18} />
            </div>
          </div>
          <p>Результаты появятся после прохождения проверок.</p>
        </div>
        <figcaption>
          Пример паспорта · иллюстрация, а не результаты участника
        </figcaption>
      </figure>
      <p className="vector-auth-demo-label">
        Локальная демонстрация ФСП Вектор
      </p>
    </aside>
  );
}
