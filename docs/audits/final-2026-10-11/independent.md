# Независимая проверка финального релиза — 11 октября 2026

Отдельный агент проверил исходное ТЗ, docs01–05, implementation contract, R01–R42,17 экспертных ответов и текущие server/frontend/engines. Рабочая БД, исходники и браузер этим агентом не менялись. Финальные browser/media/install действия выполнены root; здесь независимо прочитаны их доказательства и сверены числовые поля.

**Вывод:** в наблюдаемом source/domain/test контуре новых P0 приложения не выявлено. App/video/PDF локально готовы; окончательный package/CRC/manifest ещё pending. Repo URL/доступ жюри,презентация и platform upload не выполнены. ready_local=true,ready_for_submission=false; это не сертификация всех состояний или безопасности.

## Предметные границы и разрешённые находки

| Область | Проверено | Ограничение |
|---|---|---|
| Identity/профиль/история | Email verification,role/owner/CSRF,strict contact consent до записи,declared отдельно от confirmed; свой Unicode PDF и evidence provenance; обе истории paginated/default30/max100/true total | Импорт является проверяемым draft,не OCR/подтверждением навыков. FSP identity только явный demo registry. |
| Assessment | Persisted private form/answers,публичный DTO без oracle,review без grading,actual submit/rubric/deadline/cooldown; FAIL сохраняет старую категорию; company practice не меняет глобальный грейд | Автоматический PASS означает серверную рубрику,не human qualification. User code на Windows/API запрещён; bounded SQL/data отдельно. |
| Matching | Formal required gates,v4 статус/валидность/отзыв,FSP cap,no-FSP путь,неизменный need snapshot; company practice scoped | Synthetic labels/recall losses/negative B4 flags сохранены; оптимальность весов и реальный найм не измерены. |
| Hiring/privacy | Invite без vacancy,company-scoped accept grant,repeat не восстанавливает revoke; apply отдельный consent; closed projection и employer re-read после revoke | Уже выгруженные чужие копии не удаляются отзывом. ATS — signed local adapter,не коммерческая интеграция. |
| Обновление UI | History больше не ограничена доступом к last30. SSE/polling refresh обновляет own domain resources,сохраняя message draft и закрытый modal; generation guards исключают старые ответы | Long-running SSE soak и все browser states не измерены. Source audit не является WCAG-сертификацией. |
| Runtime/delivery | Native web/API/worker/PostgreSQL/identity/mail/ATS,typed OpenAPI/TS; repeat source install/PDF/video proof | Docker CLI есть; daemon/Compose/gVisor actual run нет. Presentation вне задачи; final package и внешняя сдача отдельно. |

Первый pagination regression падал до assertions из-за отсутствующего result незавершённой fixture. Исправлен обычным submit пустых ответов,создающим настоящий FAIL DTO; historical fixtures явно demo,не fake PASS. UI-only privacy/скрытые grade writes не обнаружены.

## Измеренные проверки

Самостоятельные targeted запуски:68tests+34subtests PASS за16,76с; после исправления pagination1PASS/19deselected; history/domain-refresh frontend8/8PASS. Они не заменяют общий прогон root и не объявляются новой проверкой после freeze.

Финальный общий root прогон:282tests+324subtests PASS за58,05с с RUN_PG_AUDIT=1,0failures,одно Starlette TestClient deprecation warning. Frontend90/90PASS за2241мс,typecheck/build PASS,HTTP smoke6/6PASS;5 profile-save cases включены. Доказательства: [release.md](release.md),[release.json](release.json),backend/frontend/engines reports.

Прочитаны [browser.json](browser.json):21desktop1440×1000+21mobile390×844; [browser-public.json](browser-public.json):ещё6views home/login/register. В обоих наборе0horizontal overflow/alert. Root проверил menu focus cycle и quality gap column. Это один local browser/два viewport,не все real devices/assistive technologies.

Прочитан повтор [source-archive.json](source-archive.json):PASS14:54:46Z после encoder correction,source commit eed113be382d8048e67a1ce1164a0f4bf65b8bf5,tested ZIP SHA9b424e3d42cfc9e2a793039b8211b6d217e77a8ebaec387ab386cac387289cb6. Fresh locked venv/pip check,npm ci/build,SQLite/Alembic,isolated API8002/web3002,same-origin login/CSRF/profile PATCH/readback. Та же Windows машина с установленными Python/Node; main stand не изменён. Проверенный runtime ZIP SHA не автоматически SHA final bundle с новыми docs/media.

## Финальный actor и доказательства медиа

Core actor final-demo-20261011@vector.local,alias9B2A98,id prefix8659E70C:actual UI registration/local SMTP verify,profile/Backend Intern survey,12UI answers/ordinary autosave/review/submit,formal100/category,publish,company match3eligible/index74,«Backend стажёр · финал ФСП Вектор»,addressed accept grant,двусторонние сообщения и revoke/closed employer re-read. Attempt c5219e57-f995-4c8b-afe0-545989434eb6. Финальный повторный вход после обеих company session switches показал backend:intern/4formal evidences100/publication без контактов. Нового restart core actor не было; прежний restart proof принадлежит release-20261011@vector.local.

Supplementary видео явно показывает другого release actor и employer:need structuring,vacancy apply/Middle с честным Intern cover letter,weekly feedback100,runner fail closed,signed local ATS,funnel/review status и quality ready. Это не результаты нового core actor. Прямой DB score/category write не использовался.

Прочитан [video.json](video.json):passed_decode_duration_fps_and_all_chapter_ui_alignment,actual207,92с/2842captures/50chapters/24fps/1440×1110. Все50midpoint UI comparisons PASS,max meanRGBerror0,7416;39reading holds,last actual frame,preparation cut,aspect letterbox. SHA da226b9df5b8b33e241c41294648c001e43f1559c70caaa278979e9c29cc9096,5914606bytes. Source actors/manifests зафиксированы. Это edited actual capture,не continuous/native/lossless video или каждое intermediate animation frame.

Исторический draft имел потерянные начальные timestamps и drift при разных физических размерах. Core перезаписан,timebase/normalization исправлены; финальный decode и50alignment samples прошли. Старые duration/SHA не считаются финальными; blocker разрешён.

[PDF proof](pdf.json):passed_unicode_text_bounds_and_sampled_visual_review,9pages/27586characters,word bounds всех9 без overflow,required Cyrillic/content tokens PASS/noPENDING. Визуально просмотрены1/5/9,не все9raster pages. SHA3c533772648bda98f43efa822a01c05497d1d46a241b4aaa0dcc34736f566dae,44583bytes.

SQL/data reference answers вычисляются из публичных условий;choice использует авторские FACTS/ledger. Это авторская structural verification,не внешняя независимая semantic/human evaluation. Human validity/IRT/form equivalence/реальные наймы/LLM attack и actual Linux isolation остаются NOT_MEASURED; negative B4 flags/retrieval loss сохранены.

Git local/private на codex/fsp-vector,remote не создан. Этот агент не публиковал и не отправлял source/competitor/runtime. После этого обновления четыре назначенных документа заморожены; root завершает private commit/package/CRC/hash gate. Презентация с обязательными слайдами7–11 — отдельный исключённый пользователем deliverable; готовность внешней сдачи не заявляется.

## Завершающая упаковка root

После заморозки независимого аудита root проверил комплект: CRC вложенного source ZIP и внешнего bundle, 276 source file hashes/размеров, все artifact hashes/размеры, текущий manual/PDF provenance, video proof и равенство runtime установленному архиву. Git чистый, remote отсутствует; ничего не отправлено. Точные факты итогового пересобранного комплекта хранятся в output/release/manifest.json и output/release/verification.json. Локальные website/video/PDF/source deliverables готовы; презентация, repo URL/доступ жюри и platform upload остаются внешними действиями. Это финальное подтверждение root, не новый запуск тестов независимым агентом.
