"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Bell,
  BriefcaseBusiness,
  Check,
  ChevronDown,
  ChevronRight,
  ContactRound,
  FileCheck2,
  Layers,
  LockKeyhole,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react";

export type PreviewMode = "bank" | "passport" | "pipeline";
const people = [
  {
    name: "Алексей Морозов",
    initials: "АМ",
    role: "Backend-разработка",
    skills: "Python · SQL · API",
    grade: "Стажёр",
    source: "Экзамен",
    tone: "blue",
  },
  {
    name: "Виктория Данилова",
    initials: "ВД",
    role: "Аналитика данных",
    skills: "Python · SQL",
    grade: "Junior",
    source: "Заявлено",
    tone: "pink",
  },
  {
    name: "Никита Соколов",
    initials: "НС",
    role: "Frontend-разработка",
    skills: "React · TypeScript",
    grade: "Junior",
    source: "Заявлено",
    tone: "orange",
  },
  {
    name: "Мария Белова",
    initials: "МБ",
    role: "Backend-разработка",
    skills: "SQL · API",
    grade: "Стажёр",
    source: "Экзамен",
    tone: "green",
  },
  {
    name: "Даниил Волков",
    initials: "ДВ",
    role: "Инженерия данных",
    skills: "Python · Git",
    grade: "Junior",
    source: "Заявлено",
    tone: "purple",
  },
];
const views = [
  { mode: "bank" as const, title: "Специалисты", icon: Users },
  { mode: "passport" as const, title: "Паспорт", icon: ContactRound },
  { mode: "pipeline" as const, title: "Воронка", icon: Layers },
];

export function ProductPreview({
  mode,
  onMode,
}: {
  mode: PreviewMode;
  onMode: (value: PreviewMode) => void;
}) {
  const reduced = useReducedMotion();
  const [selected, setSelected] = useState(0);
  const [query, setQuery] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const focusRecord = useRef(false);
  const person = people[selected];
  useEffect(() => {
    if (focusRecord.current && mode === "passport") {
      headingRef.current?.focus({ preventScroll: true });
      focusRecord.current = false;
    }
  }, [mode, selected]);
  const openPerson = (index: number) => {
    focusRecord.current = true;
    setSelected(index);
    onMode("passport");
  };
  return (
    <div
      className="attio-demo"
      aria-label="Интерактивный пример интерфейса с вымышленными данными"
    >
      <aside className="attio-demo-sidebar">
        <div className="attio-demo-team">
          <span className="attio-demo-team-mark">В</span>
          <strong>Вектор Лаб</strong>
          <ChevronDown size={12} />
        </div>
        <div className="attio-demo-search">
          <Search size={13} />
          <span>Рабочее пространство</span>
        </div>
        <div className="attio-demo-quiet">
          <Bell size={14} />
          Уведомления
        </div>
        <div className="attio-demo-quiet">
          <BriefcaseBusiness size={14} />
          Потребности команды
        </div>
        <span className="attio-demo-nav-label">Подбор и найм</span>
        <nav aria-label="Сценарий примера">
          {views.map(({ mode: value, title, icon: Icon }) => (
            <button
              key={value}
              type="button"
              aria-pressed={mode === value}
              className={mode === value ? "selected" : ""}
              onClick={() => onMode(value)}
            >
              <Icon size={14} />
              {title}
            </button>
          ))}
        </nav>
        <div className="attio-demo-sidebar-bottom">
          <ShieldCheck size={14} />
          <span>Контакты под контролем</span>
        </div>
      </aside>
      <div className="attio-demo-main">
        <header className="attio-demo-breadcrumb">
          <Users size={14} />
          <span>Моя команда</span>
          <ChevronRight size={12} />
          <strong>
            {mode === "bank"
              ? "Специалисты"
              : mode === "passport"
                ? "Паспорт компетенций"
                : "Воронка найма"}
          </strong>
          <span className="attio-demo-example">Пример</span>
        </header>
        <div className="attio-demo-heading">
          <h3 ref={headingRef} tabIndex={-1}>
            {mode === "bank"
              ? "Люди для твоей команды"
              : mode === "passport"
                ? person.name
                : "От приглашения к разговору"}
          </h3>
          <span>
            {mode === "bank"
              ? "5 специалистов"
              : mode === "passport"
                ? person.role
                : "Предложения с условиями"}
          </span>
        </div>
        <div className="attio-demo-toolbar">
          <nav aria-label="Представление примера">
            {views.map(({ mode: value, title }) => (
              <button
                key={value}
                type="button"
                aria-pressed={mode === value}
                onClick={() => onMode(value)}
              >
                {title}
              </button>
            ))}
          </nav>
          {mode === "bank" ? (
            <label className="attio-demo-filter">
              <Search size={13} />
              <input
                aria-label="Поиск в примере"
                placeholder="Имя или навык"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          ) : (
            <span className="attio-demo-private">
              <LockKeyhole size={12} />
              Контакты закрыты
            </span>
          )}
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={mode}
            className="attio-demo-content"
            initial={reduced ? false : { opacity: 0.8, y: 7 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduced ? { opacity: 1 } : { opacity: 0.8 }}
            transition={{
              duration: reduced ? 0 : 0.2,
              ease: [0.16, 1, 0.3, 1],
            }}
          >
            {mode === "bank" ? (
              <div
                className="attio-demo-table"
                role="table"
                aria-label="Пример банка специалистов"
              >
                <div className="attio-demo-table-head" role="row">
                  <span role="columnheader">Специалист</span>
                  <span role="columnheader">Направление</span>
                  <span role="columnheader">Навыки</span>
                  <span role="columnheader">Основание</span>
                  <span role="columnheader" className="sr-only">
                    Открыть
                  </span>
                </div>
                {people
                  .map((p, index) => ({ p, index }))
                  .filter(({ p }) =>
                    `${p.name} ${p.role} ${p.skills}`
                      .toLocaleLowerCase("ru")
                      .includes(query.toLocaleLowerCase("ru")),
                  )
                  .map(({ p, index }) => (
                    <div
                      className="attio-demo-table-row"
                      role="row"
                      key={p.name}
                    >
                      <div role="cell">
                        <span className={`attio-demo-avatar ${p.tone}`}>
                          {p.initials}
                        </span>
                        <button type="button" onClick={() => openPerson(index)}>
                          {p.name}
                        </button>
                      </div>
                      <span role="cell">{p.role}</span>
                      <span role="cell">{p.skills}</span>
                      <span role="cell">
                        <span
                          className={`attio-demo-tag ${p.source === "Экзамен" ? "checked" : ""}`}
                        >
                          {p.source === "Экзамен" && <Check size={10} />}
                          {p.source}
                        </span>
                      </span>
                      <span role="cell">
                        <button
                          className="attio-demo-open"
                          type="button"
                          aria-label={`Показать пример паспорта ${p.name}`}
                          onClick={() => openPerson(index)}
                        >
                          <ArrowRight size={13} />
                        </button>
                      </span>
                    </div>
                  ))}
                {query &&
                  !people.some((p) =>
                    `${p.name} ${p.role} ${p.skills}`
                      .toLocaleLowerCase("ru")
                      .includes(query.toLocaleLowerCase("ru")),
                  ) && (
                    <p className="attio-demo-no-results">
                      В этом примере нет совпадений.
                    </p>
                  )}
              </div>
            ) : mode === "passport" ? (
              <div className="attio-demo-record">
                <div className="attio-demo-record-main">
                  <div className="attio-demo-person">
                    <span className={`attio-demo-avatar large ${person.tone}`}>
                      {person.initials}
                    </span>
                    <div>
                      <strong>{person.name}</strong>
                      <span>
                        {person.role} · {person.grade}
                      </span>
                    </div>
                  </div>
                  <h4>Навыки и их основания</h4>
                  <p>
                    Каждый источник остаётся отдельным. Смотри, что проверено, а
                    что специалист указал сам.
                  </p>
                  <div className="attio-demo-evidence">
                    <FileCheck2 size={18} />
                    <div>
                      <strong>
                        {person.source === "Экзамен"
                          ? "SQL · API"
                          : person.skills}
                      </strong>
                      <span>
                        {person.source === "Экзамен"
                          ? "Формальный экзамен · Backend · Стажёр"
                          : "Навыки указаны в профиле кандидата"}
                      </span>
                    </div>
                    <span
                      className={`attio-demo-tag${person.source === "Экзамен" ? " checked" : ""}`}
                    >
                      {person.source}
                    </span>
                  </div>
                  <div className="attio-demo-evidence">
                    <ContactRound size={18} />
                    <div>
                      <strong>{person.skills}</strong>
                      <span>Самоописание · не подтверждено автоматически</span>
                    </div>
                    <span className="attio-demo-tag">Заявлено</span>
                  </div>
                  <div className="attio-demo-record-note">
                    <LockKeyhole size={15} />
                    Компания увидит контакты после отдельного согласия.
                  </div>
                </div>
                <aside className="attio-demo-properties">
                  <h4>Свойства</h4>
                  <dl>
                    <div>
                      <dt>Направление</dt>
                      <dd>{person.role}</dd>
                    </div>
                    <div>
                      <dt>Грейд</dt>
                      <dd>{person.grade}</dd>
                    </div>
                    <div>
                      <dt>Основание</dt>
                      <dd>{person.source}</dd>
                    </div>
                    <div>
                      <dt>Контакты</dt>
                      <dd>Закрыты</dd>
                    </div>
                    <div>
                      <dt>ФСП ID</dt>
                      <dd>Не связан</dd>
                    </div>
                  </dl>
                  <span className="attio-demo-property-caption">
                    Спортивные достижения дополняют профессиональную категорию.
                  </span>
                </aside>
              </div>
            ) : (
              <div className="attio-demo-board">
                {["Приглашены", "Обсуждение", "Встреча"].map((stage, i) => (
                  <section key={stage}>
                    <h4>
                      <span className={`attio-demo-stage-dot stage-${i}`} />
                      {stage}
                      <small>{i === 0 ? 2 : 1}</small>
                    </h4>
                    {(i === 0
                      ? [people[0], people[2]]
                      : i === 1
                        ? [people[3]]
                        : [people[1]]
                    ).map((p) => (
                      <button
                        type="button"
                        className="attio-demo-board-card"
                        key={p.name}
                        onClick={() => openPerson(people.indexOf(p))}
                      >
                        <span className={`attio-demo-avatar ${p.tone}`}>
                          {p.initials}
                        </span>
                        <strong>{p.name}</strong>
                        <span>{p.role}</span>
                        <span className="attio-demo-tag">
                          {p.skills.split(" · ")[0]}
                        </span>
                        <span className="attio-demo-board-lock">
                          <LockKeyhole size={11} />
                          Контакты закрыты
                        </span>
                      </button>
                    ))}
                  </section>
                ))}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
        <div className="attio-demo-footer">
          <span>Демонстрация интерфейса</span>
          <span>Вымышленные профили и компания</span>
        </div>
      </div>
    </div>
  );
}
