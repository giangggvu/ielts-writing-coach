# IELTS Writing Coach

[![CI](https://github.com/giangggvu/ielts-writing-coach/actions/workflows/ci.yml/badge.svg)](https://github.com/giangggvu/ielts-writing-coach/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue) ![License: MIT](https://img.shields.io/badge/license-MIT-green)

**English** · [Tiếng Việt](#tiếng-việt)

AI feedback and **estimated** band scores for IELTS Writing Task 2 essays. Paste a question
and your essay; the feedback appears while the model is still writing it, the band scores
are validated before they are saved, and your history shows how your bands change over time.

> Scores are AI estimates for practice only. They do not replace an IELTS examiner.

![Grading page](docs/screenshot-grade.png)

## Features

- Sign up / log in with email and password, JWT bearer tokens, Argon2 password hashing
- Grade a Task 2 essay (150 - 600 words) and get:
  - a band for each criterion: Task Response, Coherence and Cohesion, Lexical Resource,
    Grammatical Range and Accuracy
  - an overall band using the official IELTS rounding rule
  - comments per criterion with **exact quotes** of mistakes from your essay
  - 3 - 5 stronger rewrites of your own sentences
  - feedback in Vietnamese or English
- Feedback streams live (Server-Sent Events); numbers are checked with Pydantic before saving
- History: list, detail view, and a band-over-time chart
- Limits: 5 gradings per user per day plus a service-wide daily cap that protects the budget
- Plain FastAPI + Jinja2 pages and a little vanilla JavaScript, no frontend build step

## Tech stack

Python 3.12 | FastAPI | SQLAlchemy 2 (async) | Alembic | PostgreSQL | Pydantic v2 | httpx |
pytest | ruff | Docker Compose | GitHub Actions

## Quick start (Docker)

```bash
cp .env.example .env          # set JWT_SECRET; LLM_PROVIDER=fake works without any key
docker compose up --build
```

Open <http://localhost:8000>. Migrations run automatically when the app container starts.

To use a real model, edit `.env`:

| Provider                            | Settings                                                                                                                            | Free key                             |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| Google Gemini                       | `LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-flash-latest`, `LLM_API_KEY=...`                                                           | <https://aistudio.google.com/apikey> |
| Groq (or any OpenAI-compatible API) | `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=openai/gpt-oss-120b`, `LLM_API_KEY=...` | <https://console.groq.com/keys>      |

Free-tier model names and limits change often; check the provider's model list if a model is
refused (the app reports "does not know this model. Check LLM_MODEL").

## Local development

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d db                  # or any local PostgreSQL 16
alembic upgrade head
uvicorn app.main:app --reload
```

Try the API with [`requests.http`](requests.http) (VS Code REST Client or JetBrains),
or the interactive docs at <http://localhost:8000/docs>.

## Tests

```bash
pytest                                   # SQLite, fast, no setup
TEST_DATABASE_URL=postgresql+psycopg://coach:coach@localhost:5432/coach_test pytest
ruff check . && ruff format --check .
```

Tests never call a real AI service: they use a scripted `FakeProvider`, and the real
provider classes are tested against `httpx.MockTransport`. CI runs everything on PostgreSQL,
checks that the Alembic migration matches the models, and builds the Docker image.

What is covered:

| Area               | Tests                                                                                                                                                   |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Grading            | streamed `feedback` events then a validated `result`; saved and readable in history                                                                     |
| Wrong model output | retried exactly once; second failure gives a clear error, nothing saved, quota not used                                                                 |
| Provider errors    | rate limit / bad key / network → friendly message, quota not used                                                                                       |
| Limits             | 6th essay refused before calling the AI; per-user; failed attempts free for the user; global cap; **8 parallel requests cannot overshoot** (PostgreSQL) |
| Privacy            | a user gets 404 for another user's essay, empty list and empty chart                                                                                    |
| Rounding           | official examples (6.25 → 6.5, 6.125 → 6.0, 3.875 → 4.0, 6.75 → 7.0 …)                                                                                  |
| Parser             | section markers split across chunks, heading variants, code fences, invented quotes dropped                                                             |

## API

| Method | Path                   |                                                                                      |
| ------ | ---------------------- | ------------------------------------------------------------------------------------ |
| POST   | `/api/auth/register`   | create an account                                                                    |
| POST   | `/api/auth/login`      | get a bearer token                                                                   |
| GET    | `/api/auth/me`         | current user                                                                         |
| GET    | `/api/quota`           | gradings used / left today                                                           |
| POST   | `/api/essays`          | grade; `text/event-stream`: `start` → `feedback`\* → (`retry`) → `result` \| `error` |
| GET    | `/api/essays`          | history, newest first (`limit`, `offset`)                                            |
| GET    | `/api/essays/progress` | bands over time for the chart                                                        |
| GET    | `/api/essays/{id}`     | one essay with full feedback                                                         |

## Project layout

```
app/
  main.py            app factory, routers, static files
  config.py          settings from environment variables
  models.py          User, Essay (SQLAlchemy 2)
  schemas.py         request/response models + the schema the AI must satisfy
  scoring.py         official IELTS overall-band rounding
  quota.py           per-user and global daily limits (atomic reservation)
  llm/               provider layer: gemini, openai_compat, fake (tests + demo)
  grading/           prompt, streaming parser, grading service (retry, save)
  routers/           auth, essays (JSON + SSE), pages (Jinja2)
  templates/ static/ HTML, CSS, vanilla JS (streaming reader, SVG chart)
alembic/             migrations
tests/               pytest suite
```

## Design decisions

**Stream text, validate numbers.** The model answers in a small text protocol: four
`### SECTION` blocks of comments, then one `### JSON` block. A streaming parser forwards the
comment text to the browser as it arrives, but the JSON is only buffered. When the stream
ends, the JSON is validated with Pydantic (whole bands 0 - 9, 3 - 5 rewrites, known criteria).
Only then is anything written to the scores columns. This gives a fast-feeling UI without
ever storing an unvalidated number. Asking for one big JSON object would make streaming
useless (half a JSON object is not readable); asking for free text would make validation
impossible.

**Official rounding, in Decimal.** The overall band is the mean of the four criteria rounded
with the rule published by IELTS / IDP / British Council: `.25` rounds up to the next half
band, `.75` up to the next whole band, anything lower rounds down - i.e. round-half-up on a
0.5 grid, `floor(mean × 2 + 0.5) / 2`. `Decimal` avoids float edge cases. Note: IELTS
publishes this rule for the overall test score across the four skills; how examiners combine
the four Writing criteria is not public, so applying the same rule here is a documented
approximation. Criterion bands are whole numbers, as in the public band descriptors.

**Quotes must be real.** Every quoted mistake is checked against the essay (case and
whitespace-insensitive). Invented quotes are dropped and logged instead of failing the
whole grading, because one hallucinated quote should not cost the user a retry.

**Exactly one retry, only for format errors.** A malformed answer is retried once with a
stricter reminder; the browser gets a `retry` event and clears the partial text. Provider
errors (rate limit, bad key, timeout) are not retried, because retrying a rate limit
immediately just fails again. In every failure case the attempt is marked `failed` and the
user's quota is not used.

**Two different counters.** Per-user quota counts completed attempts (plus ones still
running), so users never pay for our failures. The global cap counts _every_ attempt that
reached the provider, failed ones included, because the money is spent either way. A
pending attempt older than 10 minutes stops counting for the user (e.g. after a server
restart).

**No race on the last slot.** Checking the quota and inserting the pending row happen in one
transaction under a PostgreSQL advisory lock. Without it, parallel requests could all read
"4 used" and all proceed; there is a test that fires 8 requests at once (and it fails if the
lock is removed).

**Provider layer, chosen by environment.** `LLMProvider` is a small protocol with one method,
`stream(system, prompt)`. Gemini and any OpenAI-compatible API (Groq, OpenRouter, Ollama …)
are implemented with plain `httpx` streaming, no vendor SDKs. Switching is a change of
`LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL`, no code change. Keys come only from the
environment, are sent in headers (never in URLs), and provider error bodies are not echoed
to users.

**Privacy by 404.** Someone else's essay returns the same 404 as a missing one, so ids
cannot be probed. All history queries are filtered by the owner in SQL.

**Pages without a frontend framework.** FastAPI serves Jinja2 templates; ~300 lines of vanilla
JS read the SSE stream with `fetch` (EventSource cannot send POST bodies or auth headers) and
draw the chart as inline SVG. This keeps the repository pure Python with no build step.
Trade-off: the token lives in `localStorage`, which is acceptable for a demo but an
HttpOnly cookie with CSRF protection would be the next step for production.

**Prompt injection.** The essay is wrapped in tags and the system prompt tells the model to
treat it as content only. Even if a user's essay tricks the model, the output still has to
pass the Pydantic schema, so the worst case is a wrong estimate for that user's own essay.

## Limitations and next steps

- Deployment to a public URL (planned)
- Login rate limiting and email verification
- HttpOnly cookie sessions instead of `localStorage`
- Calibrating the prompt against officially published sample essays with examiner bands

## License

[MIT](LICENSE)

---

## Tiếng Việt

Ứng dụng chấm và góp ý bài IELTS Writing Task 2 bằng AI. Dán đề và bài viết; nhận xét hiện
ra dần trong lúc mô hình đang viết, điểm band được kiểm tra trước khi lưu, và trang lịch sử
cho thấy band thay đổi thế nào qua các lần chấm.

> Điểm band chỉ là **ước tính** của AI để luyện tập, không thay thế giám khảo IELTS.

### Tính năng

- Đăng ký, đăng nhập bằng email và mật khẩu; xác thực bằng token JWT; mật khẩu băm bằng Argon2
- Chấm bài Task 2 (150 - 600 từ), trả về:
  - band ước tính cho 4 tiêu chí: Task Response, Coherence and Cohesion, Lexical Resource,
    Grammatical Range and Accuracy
  - band tổng, làm tròn theo quy tắc chính thức của IELTS
  - nhận xét từng tiêu chí, **trích nguyên văn** lỗi trong bài
  - 3 - 5 câu viết lại hay hơn
  - nhận xét bằng tiếng Việt hoặc tiếng Anh
- Nhận xét hiện dần theo luồng (Server-Sent Events); điểm số được Pydantic kiểm tra rồi mới lưu
- Lịch sử: danh sách bài, xem chi tiết, biểu đồ band qua các lần chấm
- Giới hạn: mỗi người 5 lượt/ngày, cộng mức trần tổng của cả hệ thống để không bị tốn tiền

### Chạy nhanh bằng Docker

```bash
cp .env.example .env          # đặt JWT_SECRET; LLM_PROVIDER=fake chạy được mà không cần khóa
docker compose up --build
```

Mở <http://localhost:8000>. Để dùng mô hình thật, sửa `.env` theo bảng nhà cung cấp ở phần
tiếng Anh (Gemini hoặc Groq đều có gói miễn phí).

### Kiểm thử

```bash
pytest                                   # dùng SQLite, không cần cài gì thêm
TEST_DATABASE_URL=postgresql+psycopg://coach:coach@localhost:5432/coach_test pytest
```

Kiểm thử không bao giờ gọi AI thật: dùng `FakeProvider` có kịch bản sẵn, còn các lớp nhà cung
cấp thật được thử với máy chủ HTTP giả (`httpx.MockTransport`). CI chạy toàn bộ trên
PostgreSQL, kiểm tra migration khớp với model và build image Docker.

### Các lựa chọn thiết kế

**Phát luồng chữ, kiểm tra số.** Mô hình trả lời theo một giao thức nhỏ: bốn khối nhận xét
`### TIÊU_CHÍ`, rồi một khối `### JSON`. Bộ phân tích luồng đẩy chữ nhận xét ra trình duyệt
ngay khi tới, còn JSON chỉ được giữ lại. Khi luồng kết thúc, JSON được Pydantic kiểm tra
(band nguyên 0 - 9, 3 - 5 câu viết lại, đúng tên tiêu chí) rồi mới ghi điểm vào cơ sở dữ liệu.
Nhờ vậy giao diện phản hồi nhanh mà không bao giờ lưu một con số chưa kiểm tra.

**Làm tròn chính thức, dùng Decimal.** Band tổng là trung bình 4 tiêu chí, làm tròn theo quy
tắc IELTS / IDP / British Council công bố: đuôi `.25` lên nửa band, đuôi `.75` lên band
nguyên, thấp hơn thì làm tròn xuống. Lưu ý: quy tắc này được công bố cho điểm tổng của 4 kỹ
năng; cách giám khảo gộp 4 tiêu chí Writing không được công khai, nên áp dụng cùng quy tắc ở
đây là một phép xấp xỉ có ghi rõ.

**Trích dẫn phải có thật.** Mỗi lỗi được trích đều được đối chiếu với bài viết. Trích dẫn bịa
bị loại bỏ và ghi log, thay vì làm hỏng cả lượt chấm.

**Thử lại đúng một lần, chỉ khi sai định dạng.** Câu trả lời sai định dạng được thử lại một
lần với lời nhắc chặt hơn. Lỗi từ nhà cung cấp (hết hạn mức, sai khóa, quá thời gian) thì
không thử lại. Mọi trường hợp thất bại đều không trừ lượt của người dùng.

**Hai bộ đếm khác nhau.** Lượt của từng người chỉ đếm lần chấm thành công (và lần đang chạy),
nên người dùng không phải trả cho lỗi của hệ thống. Mức trần toàn hệ thống đếm _mọi_ lần đã
gọi tới nhà cung cấp, kể cả lần lỗi, vì tiền đã tốn dù kết quả ra sao.

**Không tranh chấp lượt cuối.** Việc kiểm tra lượt và tạo bản ghi chờ nằm trong một giao dịch
có khóa advisory của PostgreSQL. Có kiểm thử gửi 8 yêu cầu cùng lúc để chứng minh không vượt
giới hạn (và kiểm thử này hỏng nếu bỏ khóa).

**Lớp nhà cung cấp, đổi bằng biến môi trường.** `LLMProvider` chỉ có một phương thức
`stream(system, prompt)`. Gemini và mọi API tương thích OpenAI (Groq, OpenRouter, Ollama…)
được viết bằng `httpx`, không dùng SDK riêng. Đổi nhà cung cấp chỉ cần sửa biến môi trường.
Khóa API chỉ đọc từ môi trường, gửi trong header chứ không nằm trong URL.

**Bảo vệ riêng tư bằng 404.** Bài của người khác trả về 404 giống như bài không tồn tại, nên
không dò được id.

**Giao diện không dùng framework.** FastAPI phục vụ template Jinja2; khoảng 300 dòng JavaScript
thuần đọc luồng SSE bằng `fetch` và vẽ biểu đồ bằng SVG. Repo vì vậy thuần Python, không cần
bước build. Đánh đổi: token lưu trong `localStorage`, đủ cho bản demo; bản chạy thật nên
chuyển sang cookie HttpOnly.

### Việc tiếp theo

- Deploy bản chạy thật
- Giới hạn số lần đăng nhập sai, xác minh email
- Hiệu chỉnh prompt bằng các bài mẫu chính thức có điểm của giám khảo

### Giấy phép

[MIT](LICENSE)
