"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Menu,
  Minus,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "motion/react";
import { Brand } from "@/components/ui";
const sources = [
  {
    label: "Экзамен",
    title: "Проверено в действии.",
    skill: "SQL · Backend",
    description:
      "В паспорте сохраняются направление, грейд и результат проверки. Работодатель видит, что именно подтверждено, и может открыть основание.",
    source: "Формальный экзамен",
    state: "Подтверждённый навык",
  },
  {
    label: "Опыт",
    title: "Твой опыт тоже имеет значение.",
    skill: "Python · опыт разработки",
    description:
      "Добавляй стек, проекты и профессиональный опыт. Заявленные навыки помогают описать тебя, а отдельная отметка показывает, какие из них ещё предстоит проверить.",
    source: "Указано участником",
    state: "Заявленный навык",
  },
  {
    label: "Достижения ФСП",
    title: "Достижение с понятным источником.",
    skill: "Спортивное программирование",
    description:
      "Спортивные результаты дополняют профессиональный профиль. Их происхождение видно отдельно: демонстрационный реестр не выдаётся за официальный реестр ФСП.",
    source: "Демонстрационный реестр",
    state: "Демооснование",
  },
];
function PassportExample() {
  return (
    <div className="vector-hero-passport">
      <div className="vector-passport-top">
        <span>Паспорт компетенций</span>
        <ArrowUpRight size={19} aria-hidden="true" />
      </div>
      <div className="vector-passport-person">
        <div className="vector-person-mark">АМ</div>
        <div>
          <h2>
            Алексей
            <br />
            Морозов
          </h2>
          <p>Backend-разработчик</p>
        </div>
      </div>
      <p className="vector-passport-intro">
        Строю понятные API.
        <br />
        Люблю задачи, в которых есть смысл.
      </p>
      <div className="vector-passport-evidence">
        <div>
          <span className="vector-proof-icon">
            <Check size={15} aria-hidden="true" />
          </span>
          <span>
            <strong>SQL / API</strong>
            <small>Формальный экзамен · Intern</small>
          </span>
        </div>
        <div>
          <span className="vector-proof-icon declared">
            <Minus size={14} aria-hidden="true" />
          </span>
          <span>
            <strong>Python</strong>
            <small>Заявлен участником</small>
          </span>
        </div>
        <div>
          <span className="vector-proof-icon registry">
            <ShieldCheck size={15} aria-hidden="true" />
          </span>
          <span>
            <strong>Достижения ФСП</strong>
            <small>Демонстрационный реестр</small>
          </span>
        </div>
      </div>
      <div className="vector-passport-bottom">
        <span className="vector-availability-dot" />
        Открыт к предложениям<span>Москва / удалённо</span>
      </div>
    </div>
  );
}
export default function Home() {
  const [employer, setEmployer] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [sourceIndex, setSourceIndex] = useState(0);
  const hero = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: hero,
    offset: ["start start", "end start"],
  });
  const progress = useSpring(scrollYProgress, { stiffness: 95, damping: 28 });
  const ribbonY = useTransform(progress, [0, 1], [0, -90]);
  const ribbonRotate = useTransform(progress, [0, 1], [-12, -3]);
  const item = sources[sourceIndex];
  return (
    <div className="vector-landing">
      <a className="vector-skip-link" href="#main">
        Перейти к содержимому
      </a>
      <header className="vector-site-header">
        <div className="vector-header-inner">
          <Brand />
          <nav aria-label="Основная навигация" className="vector-desktop-nav">
            <a href="#passport">Паспорт</a>
            <a href="#assessment">Проверка навыков</a>
            <a href="#opportunities">Вакансии</a>
          </nav>
          <div className="vector-header-actions">
            <Link href="/login" className="vector-login-link">
              Войти
            </Link>
            <Link href="/register" className="vector-site-button compact">
              Начать <ArrowUpRight size={16} aria-hidden="true" />
            </Link>
          </div>
          <button
            type="button"
            className="vector-menu-toggle"
            aria-label={mobileNav ? "Закрыть меню" : "Открыть меню"}
            aria-expanded={mobileNav}
            aria-controls="vector-mobile-nav"
            onClick={() => setMobileNav(!mobileNav)}
          >
            {mobileNav ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
        {mobileNav && (
          <nav
            id="vector-mobile-nav"
            className="vector-mobile-nav"
            aria-label="Мобильная навигация"
          >
            <a href="#passport" onClick={() => setMobileNav(false)}>
              Паспорт
            </a>
            <a href="#assessment" onClick={() => setMobileNav(false)}>
              Проверка навыков
            </a>
            <a href="#opportunities" onClick={() => setMobileNav(false)}>
              Вакансии
            </a>
            <Link href="/login">Войти в пространство</Link>
            <Link href="/register">
              Создать аккаунт <ArrowUpRight size={17} />
            </Link>
          </nav>
        )}
      </header>
      <main id="main">
        <section
          ref={hero}
          className="vector-hero"
          aria-labelledby="hero-title"
        >
          <div className="vector-hero-copy">
            <div className="vector-audience" aria-label="Для кого платформа">
              <button
                type="button"
                aria-pressed={!employer}
                onClick={() => setEmployer(false)}
              >
                Специалистам
              </button>
              <button
                type="button"
                aria-pressed={employer}
                onClick={() => setEmployer(true)}
              >
                Компаниям
              </button>
            </div>
            <h1 id="hero-title">
              {employer ? "Твой проект." : "Твой талант."}
              <br />
              <span>Твоя команда.</span>
            </h1>
            <p className="vector-hero-description">
              {employer
                ? "Найди людей, которые умеют делать. Опиши задачу команды и выбирай специалистов по понятным доказательствам навыков."
                : "Покажи, что ты умеешь. Подтверди навыки, собери профессиональный паспорт и найди команду, которой нужен именно твой опыт."}
            </p>
            <div className="vector-hero-actions">
              <Link
                className="vector-site-button"
                href={employer ? "/register?role=employer" : "/register"}
              >
                {employer ? "Найти специалиста" : "Создать свой паспорт"}
                <ArrowUpRight size={19} aria-hidden="true" />
              </Link>
              <Link href="/login" className="vector-text-link">
                Посмотреть сервис <ArrowRight size={18} aria-hidden="true" />
              </Link>
            </div>
            <p className="vector-hero-note">
              {employer
                ? "От потребности команды до диалога и найма."
                : "Можно начать без достижений ФСП."}
            </p>
          </div>
          <div className="vector-hero-scene">
            <motion.img
              src="/assets/vector-ribbon.png"
              alt=""
              aria-hidden="true"
              className="vector-hero-ribbon"
              width={1536}
              height={1024}
              fetchPriority="high"
              style={reduced ? undefined : { y: ribbonY, rotate: ribbonRotate }}
            />
            <div className="vector-credential-position">
              <PassportExample />
              <p className="vector-example-caption">
                Пример паспорта · вымышленные данные
              </p>
            </div>
          </div>
          <a href="#passport" className="vector-scroll-hint">
            <ArrowDown size={17} aria-hidden="true" />
            Знакомься с Вектором
          </a>
        </section>
        <section
          className="vector-fields"
          aria-label="Профессиональные направления"
        >
          <p>
            Опыт в разных направлениях.
            <br />
            <strong>Одна точка встречи.</strong>
          </p>
          <div>
            <span>Backend</span>
            <span>Frontend</span>
            <span>Аналитика данных</span>
            <span>Информационная безопасность</span>
            <span>DevOps</span>
            <span>QA</span>
          </div>
        </section>
        <section
          id="passport"
          className="vector-proof-section"
          aria-labelledby="passport-title"
        >
          <div className="vector-section-copy">
            <h2 id="passport-title">
              За каждым навыком —<br />
              <em>своё основание.</em>
            </h2>
            <p>
              Резюме рассказывает о тебе. Паспорт показывает, на чём основаны
              твои компетенции: опыт, экзамен или спортивное достижение.
            </p>
            <Link href="/register" className="vector-text-link">
              Собрать свой паспорт <ArrowUpRight size={19} aria-hidden="true" />
            </Link>
          </div>
          <div className="vector-evidence-inspector">
            <div
              className="vector-evidence-switch"
              aria-label="Источники навыков"
            >
              {sources.map((source, index) => (
                <button
                  type="button"
                  key={source.label}
                  aria-pressed={index === sourceIndex}
                  onClick={() => setSourceIndex(index)}
                >
                  {source.label}
                </button>
              ))}
            </div>
            <motion.div
              key={item.label}
              className="vector-evidence-detail"
              initial={reduced ? false : { opacity: 0.85, y: 7 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduced ? 0 : 0.22 }}
            >
              <div
                className={`vector-evidence-seal ${sourceIndex === 0 ? "verified" : ""}`}
              >
                {sourceIndex === 0 ? (
                  <CheckCircle2
                    size={36}
                    strokeWidth={1.4}
                    aria-hidden="true"
                  />
                ) : (
                  <ShieldCheck size={36} strokeWidth={1.4} aria-hidden="true" />
                )}
              </div>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              <div className="vector-evidence-record">
                <strong>{item.skill}</strong>
                <span>{item.state}</span>
                <div>
                  <span>Источник</span>
                  <strong>{item.source}</strong>
                </div>
              </div>
              <small>Пример записи в паспорте</small>
            </motion.div>
          </div>
        </section>
        <section
          id="assessment"
          className="vector-assessment-section"
          aria-labelledby="assessment-title"
        >
          <div className="vector-assessment-visual">
            <div className="vector-assessment-heading">
              <span>Проверка компетенций</span>
              <span>Backend · Intern</span>
            </div>
            <h3>
              Знания становятся
              <br />
              доказательствами.
            </h3>
            <div className="vector-assessment-path">
              <div>
                <span>Направление и грейд</span>
                <strong>Ты выбираешь, что проверить</strong>
              </div>
              <div>
                <span>Практические задания</span>
                <strong>Результат следует из ответов</strong>
              </div>
              <div>
                <span>Основание в паспорте</span>
                <strong>С областью и источником проверки</strong>
              </div>
            </div>
            <span className="vector-assessment-foot">
              Экзамен и тренировка сохраняются отдельно
            </span>
          </div>
          <div className="vector-section-copy">
            <h2 id="assessment-title">
              Не просто
              <br />
              <em>список технологий.</em>
            </h2>
            <p>
              Проверь навыки в выбранном направлении и грейде. После экзамена
              результат попадёт в паспорт. Тренировки помогут подготовиться и
              понять, что стоит подтянуть.
            </p>
            <Link href="/workspace/assessment" className="vector-site-button">
              Выбрать проверку <ArrowUpRight size={18} aria-hidden="true" />
            </Link>
          </div>
        </section>
        <section
          id="opportunities"
          className="vector-opportunities-section"
          aria-labelledby="opportunities-title"
        >
          <div className="vector-opportunities-heading">
            <h2 id="opportunities-title">
              Работа, которая
              <br />
              <em>подходит тебе.</em>
            </h2>
            <p>
              Ищи вакансии, смотри причины соответствия и выбирай, с кем
              продолжить разговор. Для компаний — подбор по задаче и
              доказательствам, а не только по словам в резюме.
            </p>
          </div>
          <div className="vector-opportunity-layout">
            <div className="vector-job-example">
              <div className="vector-job-company">
                <span className="vector-company-mark">В</span>
                <div>
                  <strong>Вектор Лаб</strong>
                  <span>Пример компании</span>
                </div>
                <ArrowUpRight size={24} aria-hidden="true" />
              </div>
              <h3>Backend-разработчик</h3>
              <p>
                Команда, которая строит надёжные сервисы и ценит понятный код.
              </p>
              <div className="vector-job-terms">
                <span>Удалённо</span>
                <span>Intern</span>
                <span>Python / SQL / API</span>
              </div>
              <div className="vector-job-reason">
                <Check size={18} aria-hidden="true" />
                <span>
                  <strong>Посмотри, что совпало.</strong>
                  <br />В подборе видно основание каждого навыка и чего пока не
                  хватает.
                </span>
              </div>
              <Link href="/workspace/jobs" className="vector-text-link">
                Открыть вакансии <ArrowRight size={20} aria-hidden="true" />
              </Link>
              <small>Вакансия и компания вымышлены</small>
            </div>
            <div className="vector-contact-story">
              <h3>
                Знакомство.
                <br />
                На твоих условиях.
              </h3>
              <p>
                Отклик, приглашение, диалог и этапы найма — в одном
                пространстве. Контакты открываются только выбранной компании с
                твоего согласия.
              </p>
              <div className="vector-conversation-line">
                <span className="vector-conversation-avatar">В</span>
                <p>Давай познакомимся и обсудим задачу команды.</p>
              </div>
              <div className="vector-contact-boundary">
                <ShieldCheck size={22} strokeWidth={1.5} aria-hidden="true" />
                <span>
                  <strong>Ты управляешь доступом.</strong>
                  <br />
                  Согласие на контакты можно отозвать.
                </span>
              </div>
              <Link href="/register?role=employer" className="vector-text-link">
                Вектор для компаний{" "}
                <ArrowUpRight size={19} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </section>
        <section className="vector-faq" aria-labelledby="faq-title">
          <div>
            <h2 id="faq-title">
              Всё начинается
              <br />
              <em>с ясности.</em>
            </h2>
            <p>
              Паспорт, проверка навыков и поиск работы доступны и без ФСП ID.
            </p>
          </div>
          <div className="vector-faq-items">
            <details>
              <summary>
                Что именно подтверждает экзамен?
                <ChevronDown size={19} aria-hidden="true" />
              </summary>
              <p>
                Результат проверки по конкретному направлению и грейду.
                Заявленный стек не становится подтверждённым автоматически.
                Практика под потребность компании и формальный экзамен имеют
                отдельные основания.
              </p>
            </details>
            <details>
              <summary>
                Кто видит мой профиль и контакты?
                <ChevronDown size={19} aria-hidden="true" />
              </summary>
              <p>
                Публикация профессионального профиля и доступ к контактам
                управляются отдельно. Контакты доступны только компании, которой
                ты дал действующее согласие; после отзыва доступ закрывается на
                сервере.
              </p>
            </details>
            <details>
              <summary>
                Можно ли посмотреть сервис без регистрации?
                <ChevronDown size={19} aria-hidden="true" />
              </summary>
              <p>
                На странице входа есть локальные демоаккаунты специалиста и
                работодателя. Данные вымышлены. Интеграция ФСП в локальном демо
                использует демонстрационный реестр, а не официальный API.
              </p>
              <Link href="/login" className="vector-text-link">
                Открыть демо <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </details>
          </div>
        </section>
        <section className="vector-final-cta">
          <h2>
            Опыт уже есть.
            <br />
            <em>Дай ему новый вектор.</em>
          </h2>
          <Link href="/register" className="vector-site-button">
            Создать свой паспорт <ArrowUpRight size={20} aria-hidden="true" />
          </Link>
          <p>
            Или{" "}
            <Link href="/register?role=employer">
              найти людей для своей команды
            </Link>
          </p>
        </section>
      </main>
      <footer className="vector-site-footer">
        <Brand />
        <p>
          ФСП Вектор · 2026
          <br />
          <span>Локальная демонстрация</span>
        </p>
        <Link href="/login">
          Войти в пространство <ArrowUpRight size={17} aria-hidden="true" />
        </Link>
      </footer>
    </div>
  );
}
