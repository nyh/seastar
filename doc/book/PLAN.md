# *Asynchronous Programming with Seastar* — Book Plan (draft 2)

Status: proposal for review by Nadav. Nothing here is final.
Tracking issue: https://github.com/scylladb/seastar/issues/916 (the eventual
patch says "Fixes https://github.com/scylladb/seastar/issues/916").

Changes since draft 1:
- Added a systematic API coverage audit against ScyllaDB and Redpanda
  (section 1b).
- Every chapter now lists the APIs it must cover.
- Added Appendix F, "The Seastar Toolbox".
- Chapter 30 is now built around idioms that both ScyllaDB and
  Redpanda had to invent independently.

## 1. What I studied, and what it told me

- **The old `doc/tutorial.md`** (2566 lines). Its best parts are the
  motivation, lifetime management, semaphores, gates, the exception
  pitfalls, scheduling groups and the debugging section. All of these
  survive into the book, rewritten and modernized. Its weaknesses: it
  is built around continuations, and many sections are only TODOs
  (chaining, interruption, the event loop, shared-nothing, shutdown,
  the I/O scheduler, latency, controllers). Some details are also out
  of date: `smp::count` is now deprecated, `engine().cpu_id()` was
  removed, and `boost::counting_iterator` should be `std::views::iota`.
- **The other `doc/*.md` files.** Several are good source material:
  `lambda-coroutine-fiasco.md`, `generator.md`, `io-scheduler.md`,
  `shared-token-bucket.md`, `rpc.md`, `rpc-streaming.md`, `signal.md`,
  `prometheus.md`, `io-tracing.md`, `testing.md`,
  `network-connection-load-balancing.md`,
  `reactor_backend_asymmetric_uring.md`, `io-tester.md`,
  `io-properties-file.md`, `compatibility.md` and `native-stack.md`.
  `mini-tutorial.md` has a nice "under the hood" explanation of
  continuation chains that we can reuse.
- **Seastar's headers, demos, apps and tests.** I went through every
  `[[deprecated]]` marker and the commit log since 2024. That log shows
  what is new and what is going away:
  - New: C++23/C++26 only; `import seastar;` C++ modules; the io_uring
    and asymmetric io_uring backends; an OpenSSL TLS backend; LTTng
    tracepoints; scheduling supergroups; unified CPU and I/O scheduling
    groups (API level 7); `io_intent`; `coroutine::try_future`; metric
    collectors.
  - Removed or deprecated: `later()`, `distributed<>`, the scollectd
    backend, `reactor::at_exit`, ostream formatters (replaced by
    `{fmt}`), and the old coroutine exception helpers.
- **ScyllaDB** (weighted most heavily). 2197 source files. I checked
  usage counts, `main()`'s structure, and the idioms in `utils/`.
- **Redpanda.** Its core is *source-available* under the Business
  Source License 1.1, and its enterprise features are under the
  Redpanda Community License. Neither is an OSI open-source license,
  but the source is public. We read it to learn idioms and never copy
  its code (the same rule applies to ScyllaDB). It has 3849 source
  files, uses `namespace ss = seastar`, and builds against its own fork
  `redpanda-data/seastar`. The fork has a few APIs that upstream lacks:
  `chunked_vector`, `chunked_hash_map` and a sampling CPU profiler. The
  book covers only upstream Seastar.

### 1b. The coverage audit

How it was done (the script and its data are in `research/`):
1. I extracted all 3,070 public, non-`internal` identifiers from
   Seastar's headers with ctags.
2. I counted the word occurrences of each in ScyllaDB and in Redpanda.
3. Separately, I counted calls to the methods of about 30 central
   classes (`future`, `sharded`, `semaphore`, the streams, `file`,
   `gate`, `abort_source`, `timer`, `queue` and others), plus direct
   `engine().` calls.
4. I checked every identifier used at least 3 times against this plan.
   Each one falls into one of four groups:
   - Named in a chapter's API list.
   - Covered under its parent topic. For example, all `byteorder.hh`
     functions come under "byte order", and the RPC `snd_buf`/`rcv_buf`
     come under custom serializers.
   - Listed in section 5 as deliberately omitted.
   - A false match on a generic word such as `apply`, `impl`, `hash` or
     `swap`.

   `research/unmatched.txt` lists the names that the plan doesn't
   mention literally.

We will rerun `research/audit.py` against the finished chapters before
the book is done.

Headline numbers, which drive how much weight each topic gets:

| Usage | ScyllaDB | Redpanda |
|---|---|---|
| `co_await` / `.then(` | 9,800 / 1,150 | coroutine-dominated too |
| `sharded<>` (incl. `sharded_parameter`, `local()`) | 1,470 + 1,900 `local()` | 2,600 + 3,500 `local()` |
| `abort_source` | 1,300 | 1,800 |
| semaphores (`get_units`, `semaphore_units`) / gates | 2,900 / 1,700 | heavy / 330 |
| `lowres_clock` / `manual_clock` (tests) | 320 / 144 | 1,500+ / 210 |
| `seastar::async` / thread test cases | 540 / 1,150 | 59 / 125 |
| metrics, http (`httpd` admin APIs, `json2code`) | heavy | heavy |
| `smp_service_group` | 100 | 190 |
| `chunked_fifo`, `bool_class`, `noncopyable_function`, `optimized_optional` | 10 / 190 / 330 / 80 | 190 / 245 / 250 / 70 |
| `perf_tests` (`PERF_TEST*`) | 56 | 540 |
| `queue<T>` (`push_eventually`, `pop_eventually`) | light | heavy |

**Idioms both projects reinvented on top of Seastar.** These are the
strongest evidence of what real applications need beyond the API
itself:

| Idiom | ScyllaDB | Redpanda |
|---|---|---|
| Stop on SIGINT/SIGTERM via `abort_source` | `stop_signal` in `main.cc` | `utils/stop_signal.h` |
| Stall-free operations on huge containers | `utils::clear_gently` (447 uses), `stall_free.hh` | `ssx/async_algorithm.h`, `async-clear.h` |
| No large contiguous allocations | `chunked_vector` (1,580), `managed_bytes`, `fragmented_temporary_buffer` | `chunked_vector` (in their fork), `iobuf` |
| Retry with backoff | `exponential_backoff_retry` | `backoff_policy`, `retry_chain_node` |
| Mutex and event built on semaphores and condition variables | `semaphore(1)` patterns | `ssx::mutex`, `ssx::event` |
| Serialize work onto one fiber | `serialized_action` | `ssx::work_queue`, `single_fiber_executor` |
| A service on one shard only | `only_on_shard0`, `start_single` | `ssx::single_sharded` |
| Admission control with memory and count limits | `reader_concurrency_semaphore` (1,070) | `adjustable_semaphore`, `queue_depth_control` |
| Exception-free error paths under overload | `utils::result`, `coroutine::return_exception` | `result<>`/`errc` everywhere |
| Live-updatable configuration | `updateable_value`, `observable` | config bindings |
| Barriers across operations or shards | `phased_barrier`, `cross_shard_barrier` | — |
| Detecting hung operations | (gate and semaphore diagnostics) | `ssx::watchdog` |
| Fault injection in tests | `utils::error_injection` (610) | `finjector` |
| A disk-error-checking file wrapper | `checked_file_impl` (a `file_impl` layer) | — |
| A Seastar thread pool for blocking libraries | `alien_worker` | `ssx::thread_worker` |

## 2. Typesetting: recommendation

**Source format: Pandoc Markdown**, one file per chapter. We write a
handful of small Pandoc filters and a build script, all in Python. **PDF goes
through LuaLaTeX** with a custom book template.

Why:

- **One source, every output.** Pandoc writes plain text (`-t plain`),
  Markdown (GitHub-flavored, for a browsable repo), single-page HTML, a
  multi-page website (the `chunkedhtml` writer), EPUB, and PDF. No other
  tool covers all of these as well.
- **LaTeX is still the best typesetter for a printed technical book.**
  Publishers still accept and produce it, and with KOMA-Script or
  `memoir`, `microtype` and good open fonts we get publisher-grade
  pages. Typst is a promising modern alternative, and Pandoc can target
  it too. We can keep it as a fast-preview PDF engine, but I would not
  bet the final typesetting on it yet.
- **Markdown keeps the barrier low.** Seastar developers already write
  it, it is readable as plain text even unprocessed, and the old
  tutorial and its `md2html` and `md2pdf` scripts are already Pandoc
  based.
- **Markdown's gaps for book work are each closed by a short Python
  filter.** (Decided with Nadav: Python, not Lua. Pandoc runs an
  external filter as a separate process and passes the document to it
  as JSON, which costs a second or two per build. We use Fedora's
  `python3-pandocfilters`. A tool that doesn't need Pandoc's parse,
  such as the code includer, can be a plain Python preprocessor.) These filters are the "book tools" we will develop:
  1. **Code inclusion from the real example program.** For example,
     `` ```{.cpp include="shoal@v6:src/store.cc" snippet="lookup"} ``
     pulls a tagged region from a specific version. The filter resolves
     `shoal@v6` through one setting: a git tag in the Shoal repository
     while we write, or a `v6/` directory if Seastar later keeps copies
     of the versions (see question 3). The book's source doesn't
     change either way. Every listing in
     the book then compiles, because it *is* the compiled code. This is
     the single most important tool.
  2. **Admonitions** (`::: note`, `::: warning`, `::: tip`), rendered
     as boxes in PDF and HTML and as indented labelled blocks in text.
  3. **Cross-references** to chapters, sections, listings and figures
     (or we use the existing `pandoc-crossref`).
  4. **Index terms**, which become `\index{}` in LaTeX and are dropped
     elsewhere.
  5. **API links.** In HTML, `` `seastar::sharded` `` links to the
     Doxygen page.
- **Diagrams as SVG** (hand-written or generated with Graphviz), used
  directly in HTML and converted for PDF. I'd avoid Mermaid, which
  renders poorly in print.

The runner-up was **AsciiDoc/Asciidoctor**, which O'Reilly uses. It has
book features built in, but its plain-text output is awkward, its PDF
is not TeX quality, and it is less familiar to Seastar contributors.
Writing the book directly in LaTeX would give the best PDF, but the
HTML and text outputs would be poor.

Practical note: Nadav installed `pandoc-cli` 3.7.0.2, `pandoc-pdf` and
`python3-pandocfilters` (2026-11-05), next to TeX Live 2026 (`lualatex`,
`xelatex`). A smoke test passed. It ran a Python filter and produced a
PDF with embedded fonts and C++ highlighting, plus HTML, GFM, plain text
and EPUB.

Fonts: Libertinus Serif for the text and Source Code Pro for code
(`texlive-libertinus-fonts`, `texlive-sourcecodepro`, installed by Nadav
on 2026-11-05).

A first build tool exists. `tools/build.py OUTDIR INPUT.md...` writes
PDF (KOMA-Script `scrbook`, `style/book.tex`; B5 as the book edition,
plus A4 and US Letter for printing at home, each in color or, with
`--gray`, grayscale for print and publishers), HTML
(`style/book.css`) and plain text into `build/`, which git ignores.
Every visual element we add later, such as the admonition boxes and the
diagrams, must also work in grayscale. The build's options are documented
in README.md.
It was tried on the old tutorial, which comes out at 96 pages in B5 and
90 in A4. All the LaTeX packages it needs are installed; README.md lists
them as one `dnf install` line.

## 3. The running example: "Shoal", a Redis-compatible sharded store with values on disk

**Name: Shoal** (decided with Nadav, 2026-11-05). No existing database
or key-value store uses the name. Chapter 3, where Shoal first
appears, explains the name in a short aside:
- Pronunciation: one syllable, rhymes with "goal" and "bowl". Many
  readers are not native English speakers.
- Meaning: a shoal is a group of fish that stay together. Biologists
  distinguish a shoal, where the fish keep together but each swims
  independently, from a school, which swims in coordination in the
  same direction. That describes share-nothing shards: independent, no
  shared state, no leader, yet one service.
- The sea theme: "Seastar" is a pun on C\* (Cassandra) and is also the
  name of a sea creature, so the example program swims in the same
  sea.

**Decided with Nadav (2026-11-05):** a key-value server that speaks the
Redis protocol (RESP). It starts in memory, like Redis. In Part IV its
values move to disk, using the Bitcask design (described below), so it
can hold more data than fits in memory.

Why not a plain in-memory Redis clone: Redis writes to disk (the AOF
and RDB snapshots) but reads its files back only at startup. Every
read is answered from memory, and the whole dataset must fit in RAM.
Such a clone would never do random reads, need a cache, or have
foreground reads competing with background writes, and that
competition is the heart of Seastar's I/O scheduler story. An HTTP
file or object server was the alternative we considered. It would lose
the raw-socket protocol chapters (Seastar's `httpd` does the work) and
the interesting cross-shard commands, and S3 compatibility would bring
SigV4 and XML noise. HTTP still appears: chapter 23 adds an admin API.

**Storage design (from v9): Bitcask**, the log-structured hash table
from Riak (Basho's 2010 paper):
- Each shard appends values to its own log segment files.
- An in-memory index per shard maps key → (segment, offset, length).
  Keys must fit in RAM; values need not.
- A read of an uncached value is one random DMA read.
- A write is an append. Concurrent writers share one fsync (group
  commit).
- A background merge (compaction) rewrites segments to drop
  overwritten and deleted values.
- Recovery scans the segments to rebuild the index.

Strings live on disk. Lists (for `BLPOP`) stay in memory and are made
durable by logging their operations. This detail can change when we
write chapter 16.

Keep the storage engine deliberately minimal (no range scans, no
secondary indexes, one simple merge policy), so that it doesn't crowd
out Seastar.

Why the Redis protocol:

- **Readers can use existing tools.** `redis-cli`, `valkey-cli`, any
  Redis client library, and real benchmarks (`redis-benchmark`,
  `memtier_benchmark`) all work against it from the very first version.
  Readers can benchmark Shoal against Redis or Valkey themselves.
- **It tells a good story.** Redis is famously single-threaded. "Let's
  build a Redis that uses every core" is a natural motivation for
  shard-per-core, and the reader can measure the payoff.
- **Its features map almost one-to-one onto Seastar topics:**
  - A RESP parser over `input_stream` → networking and streams.
  - Pipelining → concurrency within a connection.
  - `EXPIRE`/TTL → timers and clocks.
  - `BLPOP` → condition variables, timeouts and abort.
  - Key → shard hashing, `MGET`/`DEL k1 k2…`/`SCAN`/`DBSIZE` →
    `sharded<>`, cross-shard fan-out and `map_reduce`. A connection
    lives on one shard, but each key belongs to the shard its hash
    picks. So a single-key command may need forwarding with
    `submit_to`, a multi-key command fans out and gathers, and
    `RENAME`/`LMOVE` across shards raises atomicity questions. Real
    Redis is single-threaded and never faces this. Redis Cluster
    simply refuses multi-key commands across hash slots (`CROSSSLOT`).
  - Pub/Sub → cross-shard broadcast and bounded queues for slow
    subscribers.
  - Values on disk (Bitcask) → DMA reads and writes, alignment, group
    commit, recovery.
  - Background merge (compaction) → the I/O scheduler and scheduling
    groups, with read latency measured with and without isolation.
  - A value cache that shrinks under memory pressure → memory
    management and reclaimers, as ScyllaDB's row cache does.
  - An `INFO`/admin HTTP API → `httpd`.
  - Replication (`REPLICAOF`) → Seastar RPC.
  - TLS → `tls::`.
  - Metrics → Prometheus.
- **It differs from Seastar's existing `apps/memcached`.** That app is
  continuation-style (75 `.then(` and no `co_await`) and has no
  persistence, isolation or multi-node features. Shoal would serve as a
  modern counterpart.

**Tools for readers.** Fedora replaced Redis with Valkey, the
BSD-licensed fork made after Redis's 2024 license change.
- `sudo dnf install valkey` gives `valkey-cli`, `valkey-benchmark`, and
  `valkey-server` for comparison.
- `valkey-compat-redis` adds the `redis-cli` names.
- `python3-redis` (redis-py) is the Python client, and drives Shoal's
  pytest test suite. Like ScyllaDB's cqlpy tests, which also run
  against Cassandra, Shoal's tests can run against a real
  `valkey-server` to check compatibility.
- `memtier_benchmark` is not packaged and must be built from source,
  so it is optional.

The incremental versions live on a branch with one commit per version,
each tagged (`shoal-v0`, `shoal-v1`, …). Every version builds and runs
against `redis-cli`. The book shows snippets, rarely whole files. Each
chapter ends with **exercises** in the K&P spirit, such as "add `INCR`"
or "make `KEYS` not stall".

| Version | Chapter | What it adds |
|---|---|---|
| v0 | 3 | skeleton: `app_template`, options, logging |
| v1 | 4 | single-shard RESP server: PING, ECHO, GET, SET, DEL, EXISTS |
| v1.1 | 5 | `KEYS` that stalls, then fixed by yielding; stall-free `FLUSHALL` |
| v2 | 7 | pipelined requests with ordered replies; MGET/MSET |
| v3 | 9 | TTL: EXPIRE, TTL, PERSIST, `SET … EX`; an active-expiry fiber |
| v4 | 10 | lists and `BLPOP`; connection limits and admission control |
| v5 | 11 | graceful shutdown that drains in-flight requests |
| v6 | 13 | `sharded<store>`, key→shard hashing, request forwarding |
| v7 | 14 | multi-key commands, `SCAN`, `DBSIZE`, `FLUSHALL`; Pub/Sub |
| v8 | 15 | `consume()`-based zero-copy parser; TLS |
| v9 | 16 | values on disk: Bitcask segments, key index, DMA reads, group commit; recovery |
| v10 | 17–18 | background merge (compaction) isolated from reads; measured p99 |
| v11 | 19 | value cache, evicted under memory pressure |
| v12 | 23 | HTTP admin API |
| v13 | 24 | primary→replica replication over Seastar RPC |
| v14 | 25 | metrics |
| — | 26 | the test suite (built up throughout, discussed here) |

## 4. Table of contents

Page counts are rough; the total is about 440 pages. Each chapter lists
**APIs** it must cover, from the audit. These lists are a checklist for
the author, not the order of the prose.

### Front matter
- **Preface.** Written 2026-11-05: what the book teaches, who it is for,
  C++ corners, what you need, Shoal, the parts, the appendices, the
  exercises, reporting mistakes. No subheadings, no conventions paragraph
  (the `seastar::` convention is chapter 3's), and no license until one is
  chosen (Nadav).

**Audience and C++ policy.** The book assumes the reader knows C++. It
is not a C++ book, but it does teach the less familiar language features
a Seastar programmer cannot do without, in the chapter where each one
is first needed:
- C++20 coroutines: what the compiler does with a coroutine, the
  coroutine frame, and why references are dangerous (chapters 4 and 8).
- Move semantics, `unique_ptr` and reference counting, explained from
  the point of view of asynchronous lifetimes (chapter 8).
- Lambda captures (by value, by reference, init-capture with
  `std::move`, `mutable`) and C++23 "deducing this" (chapters 8 and
  22).
- Concepts and `{fmt}`, only as needed.

These appear as short "C++ corner" sidebars, so readers who already
know the material can skip them. Nadav asked (2026-11-05) that the
book explain the Lambda Coroutine Fiasco (`doc/lambda-coroutine-fiasco.md`),
and in general the C++ facts that most programmers never learn but
that Seastar code runs into. The catalog below assigns each one to the
chapter where it first bites. Appendix G collects them all as a quick
reference.

| C++ corner | Chapter |
|---|---|
| **What a coroutine is made of:** the heap-allocated frame, what is copied into it (parameters) and what is not (whatever references point to). Awaiting a ready future does not suspend, so a loop of ready futures never yields. | 4, 5 |
| **Coroutine parameters taken by reference** dangle once the caller's temporaries die. Awaiting at once is safe, because temporaries live to the end of the full expression; storing the future and awaiting later is not. The rule: take parameters by value unless the caller awaits immediately. | 4, 8 |
| **No `co_await` inside a `catch` block** (C++20 forbids it). Save the `std::exception_ptr`, leave the handler, then await. ScyllaDB code is full of this pattern. | 4, 11 |
| **Constructors and destructors cannot `co_await`.** Hence asynchronous factory functions (`static future<T> create()`) and explicit `stop()`/`close()` methods: RAII cannot wait, so asynchronous cleanup needs `deferred_stop`, `deferred_close`, gates and `with_closeable`. | 8, 11 |
| **The Lambda Coroutine Fiasco.** A lambda coroutine's captures live in the lambda object, which the coroutine reaches through a reference; when an API such as `then()` destroys the lambda after its first suspension, the captures dangle. The cure is C++23's `this auto` ("deducing this"), which moves the captures into the coroutine frame. Seastar now requires C++23, so the cure is always available; the older `coroutine::lambda` and `std::ref` workarounds are taught only so readers recognize them (ScyllaDB has both, in 22 files and 25 lambdas). | 8 |
| **Every suspension point is a place where the world can change.** References and iterators into shared containers can be invalidated across a `co_await` by another fiber. | 7, 8 |
| **Evaluation order.** C++17 sequences `a` before `c` in `a.b(c)`, so `p->get().then([p = std::move(p)] …)` is safe, but function arguments are still unordered, so `f(std::move(p), p->size())` is not. | 8, 22 |
| **Moving from a capture in a non-`mutable` lambda silently copies,** because captures are `const`. | 22 |
| **Discarded futures:** `[[nodiscard]]`, what fire-and-forget really costs, and how to do it deliberately with a gate. | 6, 7 |
| **`noexcept` matters:** `future<T>` requires `T` to be nothrow-move-constructible (a `static_assert`), and `std::vector` copies instead of moving elements whose move constructor isn't `noexcept`. | 6, 19 |
| **Move-only callables:** `std::function` requires copyable callables, so Seastar has `noncopyable_function`. | 6 |
| **Non-atomic reference counting:** `seastar::shared_ptr` and `lw_shared_ptr` are cheap because they aren't thread-safe, so they must never cross shards; `foreign_ptr` is the cross-shard wrapper. Also `lw_shared_ptr` vs. `shared_ptr` (no polymorphism vs. polymorphism). | 8, 13 |
| **`thread_local` means per shard,** and static initialization and destruction order traps. | 12 |
| **Exceptions are expensive** (stack unwinding, and historically a global lock in the unwinder), so Seastar offers `make_exception_future`, `coroutine::exception` and result types. | 11 |
| **Hidden large allocations:** `std::unordered_map` buckets, `std::vector` growth and `std::string`, and how chunked containers avoid them. | 19 |
| **Member declaration order is destruction order,** which matters for gates, services and their stop order. | 11, 14 |
| **Reading concept-constrained error messages** from Seastar's templates. | 3, 6 |
| **Name clashes with `std`** (`shared_ptr`, `make_shared`, `future`, `promise`) under `using namespace seastar` (question 5). | 3 |

### Part I — Why Seastar

1. **The Case for Seastar** (14 pp). The hardware shift: many cores,
   NVMe drives doing millions of IOPS, 100 Gb/s NICs. What sharing
   costs (locks, atomics, cache-line bouncing, context switches). How
   servers evolved: thread per connection, then event loops, then shard
   per core. What Seastar gives you: share-nothing shards, a userspace
   cooperative scheduler, futures and coroutines, and its own CPU and
   I/O schedulers. What it asks in return: never block, C++, Linux,
   owning the machine. **A brief history and the license** (about two
   pages):
   - Avi Kivity, named explicitly: KVM's original lead developer, who
     created Seastar at Cloudius Systems (the makers of OSv) after
     seeing how Cassandra's architecture held back its performance.
     His first commit is dated 2014-08-10. The name is a pun on C*.
   - The OSv experience that led to it, and the open-source release.
   - ScyllaDB built on Seastar; the company then renamed itself
     ScyllaDB.
   - Adoption by Redpanda, Ceph and others.
   - Who maintains it today.
   - The Apache 2.0 license: you may build open-source or proprietary
     software on it, and it includes a patent grant. `NOTICE` lists
     the BSD-licensed parts from OSv and DPDK.

   A short teaser of what has been built with it, with headline
   numbers. It starts with ScyllaDB, because Seastar was created for
   ScyllaDB's needs, and ScyllaDB is still its largest user and main
   driver. Then Redpanda and Ceph Crimson, and a pointer to the full
   survey in chapter 29. Meet Shoal.
2. **A Tutorial Introduction** (16 pp). A K&R chapter-1 style whirlwind:
   hello world, shard count, a coroutine that sleeps, then a 40-line
   echo server running on all cores, benchmarked. Every concept appears
   briefly and is covered properly later.

### Part II — Coroutines on One Shard

3. **Getting Started** (16 pp). **Getting Seastar and living with it.**
   Seastar rarely makes releases (six tags so far, the latest
   `seastar-25.05.0`), so applications pin a commit, as a submodule
   like ScyllaDB or a fork like Redpanda. Then the compatibility
   policy from `compatibility.md`: source compatibility but not link
   compatibility, the last two C++ standards and compilers, the
   deprecation process, and API levels. Then the community: GitHub
   issues, discussions and pull requests, and how to contribute (not the
   seastar-dev mailing list, which is no longer really used: Nadav,
   2026-11-05). Then
   building Seastar (or using a package).
   A project skeleton with CMake or pkg-config, plus `import seastar;`.
   Namespace conventions (`seastar::`, unqualified, Redpanda's `ss::`),
   the clashes with `std`, and the book's choice (question 5).
   **The C++ this book assumes** (about one page): C++23, the oldest
   standard Seastar still supports. Seastar supports the last two ISO
   standards (C++23 and C++26 since August 2026) and the last two major
   releases of GCC and Clang (`doc/compatibility.md`, `BUILD.md`). It
   lists the newer features the book relies on and where each is
   explained: coroutines, concepts, modules and `std::source_location`
   (C++20), and deducing this (C++23). It notes that nothing in the book
   needs C++26.
   Covers `app_template`, `-c` and `-m`, user options and
   `SEASTAR_OPTIONS`, and the logger. *Shoal v0*, introduced with a
   short aside on the name: how to pronounce it, what a shoal is (as
   opposed to a school), and the sea theme it shares with Seastar
   (section 3).
   *APIs:* `app_template` (`config`, `add_options`,
   `add_positional_options`, `configuration()`, `run`),
   `program_options::string_map` and `get_or_default`, `logger` and
   `log_level` (`is_enabled`, `level_name`), `log_cli` options
   (`get_options_description`, `logging_settings`), `smp::shard_count()`
   and `this_smp_shard_count()` (the replacement for `smp::count`, with
   951 uses in ScyllaDB), `this_smp_all_shards()`, `this_shard_id()`,
   `smp_options` (`memory_allocator`).
4. **Coroutines** (22 pp). `future<T>` as the return type; `co_await`
   and `co_return`; composing coroutines; exceptions; the fast error
   path; the accept loop and per-connection coroutines; `input_stream`
   and `output_stream` just deep enough for RESP. *Shoal v1, which
   works with `redis-cli`.* Opens with a short note: Seastar was
   designed around continuations, because coroutines didn't exist in
   C++ yet, and it gained coroutine support in 2019, before C++20
   standardized them. The full story is in chapter 22.
   *APIs:* `coroutine.hh`, `coroutine::try_future`,
   `coroutine::as_future`, `coroutine::exception`,
   `coroutine::return_exception` and `return_exception_ptr`, `listen`,
   `server_socket::accept`, `connected_socket::input()`/`output()`,
   `read`, `write`, `flush`, `close`, `temporary_buffer` basics,
   `sstring`.
5. **How Seastar Runs Your Code** (18 pp). The reactor loop, tasks and
   polling. Cooperative scheduling, preemption points and the task
   quota. `maybe_yield`, `need_preempt` and the stall detector
   (`--blocked-reactor-notify-ms` and its runtime update). What "never
   block" really means: no `std::mutex`, no blocking system calls, no
   huge loops, no giant allocations, and no destroying a huge container
   in one go. That last one is the `clear_gently` lesson, which both
   ScyllaDB and Redpanda had to learn. Why there are no data races
   within a shard, yet state can still change at every `co_await`.
   **Where exactly preemption can happen** (Nadav, 2026-11-05), as a
   table, checked against `coroutine.hh` and `future.hh`:
   - `co_await` on a future that isn't ready always suspends.
   - `co_await` on a ready future is a preemption point: it yields if
     the task quota (`--task-quota-ms`, default 0.5 ms) is used up, and
     otherwise continues at once. So every `co_await` is a potential
     preemption point, and a loop of `co_await`s yields by itself.
   - `co_await coroutine::without_preemption_check(f)` skips that check
     (unused in ScyllaDB).
   - `then()` on a ready future runs the continuation at once and never
     checks the quota (in optimized builds; debug builds always go
     through the scheduler), so a chain of ready continuations never
     yields (chapter 22).
   - `future::get()` in a Seastar thread doesn't check the quota either
     when the future is ready; only `thread::maybe_yield()` does
     (chapter 20).
   - Explicit points: `coroutine::maybe_yield()` and
     `thread::maybe_yield()` (yield only if the quota is used up),
     `seastar::yield()` (always), and `need_preempt()` to check.
   Chapters 20, 21 and 22 build on this table and refer back to it.
   *Shoal v1.1.*
   *APIs:* `coroutine::maybe_yield`, `need_preempt`,
   `coroutine::without_preemption_check`, `seastar::yield`,
   `check_for_io_immediately`, the
   reactor's stall-notification settings.
6. **Futures and Promises** (18 pp). What a coroutine returns. Future
   states, ready futures, `make_ready_future`. `promise<T>`,
   `shared_future` and `shared_promise`. Futures are single-use.
   Discarded futures and the "exceptional future ignored" warning. The
   cost model: when a plain future-returning function beats a coroutine
   on a hot path.
   *APIs:* `make_ready_future`, `make_exception_future`,
   `current_exception_as_future`, `as_ready_future`, `available()`,
   `failed()`, `get_exception()`, `ignore_ready_future()`,
   `discard_result()`, `forward_to`, `promise::set_value` and
   `set_exception`, `shared_promise::get_shared_future`,
   `shared_future::valid`, `broken_promise`, `nested_exception`,
   `futurize`/`futurize_t`, `is_future`
   (briefly).
7. **Concurrency Within a Shard** (20 pp). Fibers and background work,
   and the dangers of fire-and-forget. Fan-out and fan-in.
   *Shoal v2: pipelining.*
   *APIs:* `coroutine::all`, `coroutine::parallel_for_each`,
   `max_concurrent_for_each`, `when_all`/`when_all_succeed`,
   `map_reduce` (with `adder` and custom reducers), `stop_iteration`.
8. **Object Lifetime in Asynchronous Code** (22 pp). This is the number
   one source of bugs. References across suspension points. Coroutine
   parameters taken by reference, and the "caller keeps it alive until
   the future resolves" convention. Lambda coroutines, the fiasco, and
   the `this auto` cure (C++23). Ownership of `temporary_buffer`.
   Catching mistakes with debug mode and ASan. Includes a bug planted in
   Shoal and found.
   *APIs:* `lw_shared_ptr`/`make_lw_shared`, `shared_ptr`/`make_shared`,
   `enable_lw_shared_from_this`/`enable_shared_from_this`,
   `static_pointer_cast`/`dynamic_pointer_cast`, `weak_ptr` and
   `weakly_referencable`, `checked_ptr`, `coroutine::lambda`, `do_with`
   (pointer to chapter 22).
9. **Time** (14 pp). Clocks, timers, sleeping, timeouts and abort
   sources. *Shoal v3: TTL.*
   *APIs:* `steady_clock_type`, `lowres_clock`, `lowres_system_clock`,
   `manual_clock` (`advance`), `timer` (`set_callback`, `arm`, `rearm`,
   `arm_periodic`, `cancel`, `armed`, `get_timeout`), `sleep`,
   `sleep_abortable` and `sleep_aborted`, `with_timeout` and
   `timed_out_error`, `abort_on_expiry`, `abort_source` (`subscribe`
   and `subscription`, `request_abort`, `request_abort_ex`,
   `abort_requested`, `check`, `abort_requested_exception`).
10. **Coordination** (26 pp). Semaphores for limiting concurrency and
    resources, and the exception types they raise. Mutex and event
    patterns (both large projects wrote their own). Admission control
    as a design: memory plus count limits, queueing and timeouts, in
    the spirit of ScyllaDB's `reader_concurrency_semaphore`.
    *Shoal v4: `BLPOP` and limits.*
    *APIs:* `semaphore` (`wait`, `signal` only as warnings), `get_units`,
    `try_get_units`, `consume_units`, `semaphore_units`,
    `with_semaphore`, `available_units`, `waiters`, `broken()`,
    `named_semaphore` and its exception factory
    (`named_semaphore_exception_factory`,
    `semaphore_default_exception_factory`, `basic_semaphore` with a
    custom factory), `broken_semaphore`, `semaphore_timed_out`,
    `semaphore_aborted` and their `named_*` variants; `condition_variable`
    (`wait` with predicate and timeout, `signal`, `broadcast`, `when()`
    for coroutines, `condition_variable_timed_out`,
    `broken_condition_variable`); `shared_mutex`, `with_lock` and `get_shared_lock`;
    `rwlock` (`hold_read_lock`, `hold_write_lock`, `try_*`); `gate` and
    `named_gate` (`hold`, `try_hold`, `holder`, `close`, `is_closed`,
    `check`, `get_count`, `with_gate`, `try_with_gate`,
    `gate_closed_exception`); `queue<T>` (`push_eventually`,
    `pop_eventually`, `abort`); `pipe` and `broken_pipe_exception`; `expiring_fifo`.
11. **Errors and Clean Shutdown** (20 pp). Thrown exceptions versus
    exceptional futures. Exception-free error handling
    (`coroutine::as_future`, `coroutine::try_future`,
    `coroutine::return_exception`) is presented as normal modern style,
    not as an optimization: it is rising fast in ScyllaDB's new code
    (`research/recent_usage.md`). **What exceptions cost under overload**: the
    exception storm, and the fixes (`as_future`, `return_exception`,
    result types such as `std::expected`), as both large projects
    learned. Internal errors. Signals. Ordered shutdown, including the
    `stop_signal` idiom both projects reinvented. *Shoal v5.*
    *APIs:* `on_internal_error`, `on_internal_error_noexcept`,
    `on_fatal_internal_error`, `set_abort_on_internal_error`,
    `throw_with_backtrace`, `make_backtraced_exception_ptr`,
    `current_backtrace`, `handle_signal`,
    `app_template::config::auto_handle_sigint_sigterm`, `closeable`,
    `deferred_close`, `deferred_stop`, `with_closeable`, `defer` and
    `deferred_action`.

### Part III — Many Cores

12. **Shared Nothing** (14 pp). States Seastar's assumption that all
    shards have equal capacity (equal memory, equal share of connections,
    no awareness of fast and slow cores), and what happens when it's
    false (Nadav, 2026-11-05). Memory divided per shard and Seastar's
    allocator. Why atomics and `std::shared_ptr` are out. Freeing on
    the wrong shard. Moving ownership across shards.
    *APIs:* `this_shard_id`, `shard_id`, `smp::all_shards()`,
    `foreign_ptr` (`make_foreign`, `get_owner_shard`, `copy`, `release`,
    `reset`, `destroy`), `file_handle` for moving files between shards,
    `sstring`.
13. **Talking Between Shards** (22 pp). Message passing, the `sharded<T>`
    service and its lifecycle, cross-shard deadlocks, and what a hop
    costs. Single-shard services (`start_single`, and the "only on shard
    0" pattern). Sharded values without a lifecycle. *Shoal v6.*
    *APIs:* `smp::submit_to`, `smp::invoke_on_all`,
    `smp::invoke_on_others`, `smp_submit_to_options`; `sharded<T>`
    (`start`, `start_single`, `stop`, `local`, `local_shared`,
    `local_is_initialized`, `invoke_on`, `invoke_on_all`,
    `invoke_on_others`, `map`, `map_reduce`, `map_reduce0`,
    `container()`, `no_sharded_instance_exception`), `sharded_parameter`, `peering_sharded_service`,
    `async_sharded_service`; `smp_service_group`
    (`create_smp_service_group` with `smp_service_group_config`,
    `default_smp_service_group`,
    `destroy_smp_service_group`).
14. **Designing a Sharded Application** (20 pp). Data partitioning. Uneven
    shard capacity, like uneven load, leaves cores idle: the slowest shard
    sets the pace. The
    shard that owns a connection versus the shard that owns the data.
    The listener load-balancing algorithms (`connection_distribution`,
    `port`, `fixed`). Shard-aware clients. Multi-key operations: fan
    out, gather, partial failure. Hot spots. Cross-shard broadcast and
    in-process publish/subscribe. *Shoal v7.*
    *APIs:* `listen_options::lba`, `stream<T>` and `subscription<T>`
    (core/stream.hh), a cross-shard barrier pattern.

### Part IV — I/O

15. **Networking in Depth** (24 pp). Sockets and options, the streams
    in depth, zero copy, **writing your own `data_source` and
    `data_sink`** (as both large projects do), stream utilities,
    addresses, DNS, TLS (both backends, certificate reloading). UDP and
    Unix sockets. The native stack and DPDK, in brief. *Shoal v8.*
    *APIs:* `listen_options` (incl. `transport` for TCP or SCTP),
    `accept_result`, `connect`, `socket` (connect with options,
    `shutdown`), `connected_socket` (`set_nodelay`, `set_keepalive`,
    `tcp_keepalive_params`, `shutdown_input`/`output`, `local_address`),
    `socket_address`, `ipv4_addr`/`ipv6_addr`, `unix_domain_addr`,
    `net::inet_address`, `net::ipv4_address`/`ipv6_address`,
    `net::dns::resolve_name`/`get_host_by_name` and `hostent`;
    `input_stream` (`read`, `read_exactly`, `read_up_to`, `skip`, `eof`,
    `consume` with `consumption_result`, `continue_consuming`,
    `stop_consuming` and `skip_bytes`, `detach`); `output_stream`
    (batching, `write` of buffers, `flush`, `close`); `data_source` /
    `data_source_impl`, `data_sink` / `data_sink_impl`, `deleter`,
    `temporary_buffer` (`share`, `trim`, `trim_front`, `prefix`,
    `clone`, `get_write`), `util::memory_data_source`/`memory_data_sink`,
    `make_object_deleter`, `as_input_stream`, `copy_n`,
    `util::read_entire_stream`, `read_entire_stream_contiguous`,
    `skip_entire_stream`;
    `tls` (`credentials_builder`, `certificate_credentials`,
    `server_credentials`, `x509_crt_format`, `tls_version`,
    `reload_callback`, `verification_error`, `tls::listen`/`connect`);
    UDP channels.
16. **Files and Storage** (24 pp). Why O_DIRECT and DMA, and alignment.
    The file API, durability (`flush`, and **`sync_directory` after
    creating or renaming a file**), group commit, file streams,
    directories, file-system queries, temporary files. Wrapping a file
    with your own `file_impl`, for example to check for disk errors as
    ScyllaDB does. *Shoal v9: values move to disk (Bitcask segments,
    a key index, DMA reads, group commit, recovery).*
    *APIs:* `open_file_dma`, `open_flags`, `file_open_options`,
    `with_file`, `with_file_close_on_failure`, `file` (`dma_read`,
    `dma_read_exactly`, `dma_read_bulk`, `dma_write`, `size`, `stat`,
    `truncate`, `allocate`, `discard`, `flush`, `close`, `dup`,
    `list_directory`, the `*_dma_alignment` queries),
    `allocate_aligned_buffer`, `make_file_input_stream` and
    `file_input_stream_options` (read-ahead, history),
    `make_file_output_stream` and `file_output_stream_options`,
    `file_input_stream_history`, `make_file_data_source`,
    `make_file_data_sink`; `util::read_entire_file(_contiguous)`;
    `file_exists`, `file_accessible` (`access_flags`), `file_stat` and
    `stat_data`, `file_size`, `file_type`, `follow_symlink`,
    `rename_file` (`rename_flags`), `link_file`, `remove_file`,
    `make_directory`, `touch_directory`, `recursive_touch_directory`,
    `recursive_remove_directory`, `open_directory`, `sync_directory`,
    `fs_avail`, `fs_type`, `directory_entry` and
    `directory_entry_type`, `file_permissions`; `tmp_file`,
    `make_tmp_file`, `tmp_dir`; `file_impl`, `layered_file`,
    `file_handle_impl`.
17. **The I/O Scheduler** (14 pp). `iotune` and `io_properties`. The
    token-bucket model in brief (from `io-scheduler.md`) and the latency
    goal. I/O classes, now unified with scheduling groups. *Shoal v10,
    part 1: the merge's writes slow down reads until it gets its own
    I/O class.*
    *APIs:* `io_intent` cancellation, `io_tester`, I/O statistics
    (`get_io_stats`, the `io_queue` metrics), LTTng I/O tracepoints.

### Part V — Isolation and Performance

18. **Scheduling Groups** (20 pp). CPU shares, and how the group is
    inherited through continuations, `submit_to`, threads and RPC.
    Supergroups. Dynamic shares, with backlog controllers. Per-group
    data. Execution stages. *Shoal v10, part 2: the merge in its own
    scheduling group, with a measured p99 read-latency improvement.*
    *APIs:* `create_scheduling_group`, `destroy_scheduling_group`,
    `default_scheduling_group`, `current_scheduling_group`,
    `with_scheduling_group`, `coroutine::switch_to`, `set_shares`,
    `get_shares`, `name`/`short_name`, `rename_scheduling_group`,
    `active`, `scheduling_supergroup`, `scheduling_group_key` (via
    `make_scheduling_group_key_config`, `scheduling_group_key_config`,
    `scheduling_group_key_create` and `scheduling_group_get_specific`),
    `thread_attributes::sched_group`, `sched_clock`,
    `thread_cputime_clock`,
    `execution_stage` and `inheriting_concrete_execution_stage`,
    scheduler statistics.
19. **Memory** (18 pp). Sizing memory per shard. Large-allocation
    warnings and why contiguous memory is the enemy: chunked containers
    and fragmented buffers, as in ScyllaDB's `chunked_vector` and
    `managed_bytes`. Reclaimers, OOM diagnostics, the sampling memory
    profiler, allocation-failure injection. *Shoal v11: a value cache
    that a reclaimer shrinks under memory pressure.*
    *APIs:* `memory::stats` and `statistics`, `free_memory`,
    `min_free_memory`, `scoped_large_allocation_warning_threshold`,
    `scoped_critical_alloc_section`, `reclaimer` and
    `reclaiming_result`, `sampled_memory_profile` and
    `allocation_site`, `with_allocation_failures` and
    `alloc_failure_injector`, `local_failure_injector`, `on_alloc_point`,
    `set_abort_on_allocation_failure` and
    `disable_abort_on_alloc_failure_temporarily`, memory diagnostics on
    OOM (`memory_diagnostics_writer`), `memory_layout`, `chunked_fifo`,
    `circular_buffer`.
20. **Seastar Threads and the Outside World** (16 pp).
    `seastar::thread`, `async`, `.get()`, `thread::yield`,
    `thread_attributes` (stack size, scheduling group), and where
    threads fit today. In request paths, coroutines have replaced them
    (`seastar::async` is rare in ScyllaDB's new code), but threads remain
    the right tool in three places: the control plane (as in ScyllaDB's
    `main()`), tests, and **long synchronous code that needs yield
    points** (Nadav): code that isn't asynchronous, such as a parser, can
    run in a thread and call `thread::maybe_yield()` to avoid stalls.
    ScyllaDB's Alternator parses large JSON requests this way, running
    RapidJSON in a thread whose handler yields between values
    (`rjson::parse_yieldable`); its SSTable writer, compaction and repair
    also yield from threads.
    Talking to non-Seastar threads (`alien::instance`,
    `alien::run_on`, `alien::submit_to`). Running blocking libraries in
    a worker thread (the `alien_worker` and `thread_worker` pattern).
    Spawning processes (`spawn_process`, `spawn_parameters`,
    `process::wait`; no longer experimental since Seastar commit
    d9901daf9, though ScyllaDB still spells it `experimental::process`).
21. **Stalls: Finding and Preventing Them** (18 pp). Added at Nadav's
    request (2026-11-05). What a stall is and why it hurts: the task
    quota, and how one long task delays every connection, timer and
    background job on its shard, the I/O scheduler's dispatching, and
    other shards waiting for answers. Where stalls come from: long loops
    over big containers, destroying huge objects, large contiguous
    allocations, copying big values, sorting, parsing big inputs,
    formatting huge log messages, exception storms, blocking system calls
    and page faults. Fixes, from simplest to heaviest:
    `coroutine::maybe_yield()` and preemption checks in loops; splitting
    work; gentle clearing and destruction of big containers (the pattern
    both ScyllaDB and Redpanda reinvented: `clear_gently`,
    `async_clear`); chunked containers; long synchronous code (a parser)
    in a Seastar thread that calls `thread::maybe_yield()`, as
    Alternator's JSON parser does (chapter 20); moving what can't yield
    to an OS thread (chapter 20). Detection: the stall detector's options
    (`--blocked-reactor-notify-ms` and related), reading a stall report
    and decoding it with `seastar-addr2line`, the relevant metrics,
    finding stalls in tests and with `perf`. Shoal: a stall hunt on a
    large dataset (deleting a list of millions of elements, `FLUSHALL`
    with many keys), with no new Shoal version. Chapter 5 keeps the
    first introduction (the `KEYS` stall of Shoal v1.1) and points here;
    chapter 27 keeps only the general debugging tools.
### Part VI — More Seastar

22. **Continuations** (20 pp, down from 26). Not only a style of older code
    (Nadav, 2026-11-05): continuations are still the faster way to write
    some code. In optimized builds, `then()` on a future that is already
    available calls the continuation at once, allocating no task, while
    a coroutine allocates its frame on every call even if every future
    it awaits is ready. So a small, hot function that mostly sees ready
    futures, or one that just transforms a future, is cheaper as a
    continuation or as a plain function returning a future. The caveat:
    that fast path doesn't check for preemption, so a long chain of
    ready continuations never yields (see the stalls chapter). The
    chapter also serves readers of existing code: ScyllaDB is removing
    `.then()` faster than it adds it, and new code almost never uses the
    loop helpers, so `repeat`, `do_until` and `keep_doing` get
    recognition-level treatment only. Opens with **Seastar and C++: a short
    history** (about two pages), explaining why continuation code looks
    the way it does. Each language feature arrived to fix a pain point,
    and ScyllaDB's code shows layers from every era. The dates come from
    Seastar's git history:
    - **C++11** gave lambdas, rvalue references and move semantics,
      `unique_ptr`, variadic templates and `std::function`, the raw
      material of futures and continuations.
    - **C++14** gave init-capture (`[buf = std::move(buf)]`), without
      which a continuation cannot own a move-only object, and generic
      lambdas. Seastar's first commit (Avi Kivity, 2014-08-10) already
      compiled with `-std=gnu++1y`, the C++14 draft.
    - **C++17**, Seastar's default from December 2017, gave guaranteed
      evaluation order in chained calls (which makes
      `p->get().then([p = std::move(p)] …)` safe), structured bindings,
      `if constexpr`, `optional`, `variant` and `string_view`.
    - **Coroutines:** Seastar support was added on 2019-01-08 (Paweł
      Dziepak), on the Coroutines TS, before **C++20** standardized
      coroutines together with concepts and modules.
    - **The Lambda Coroutine Fiasco** was documented and mitigated
      (`coroutine::lambda`) in September 2022. **C++23**'s deducing
      this (`this auto`) cures it.
    - **The standards supported:** C++20 and C++23 from January 2024
      (C++17 dropped), then C++23 and C++26 from August 2026 (C++20
      dropped).

    Idioms such as `do_with`, `repeat` and `then_unpack` were
    workarounds for what the language lacked. Knowing that makes old
    code easier to read and modernize.
    Then everything the old tutorial taught,
    refreshed: `then()` and chaining, captures and `mutable`,
    `then_wrapped`, `finally`, `handle_exception` and
    `handle_exception_type`, `futurize_invoke`, the
    throw-versus-exceptional-future pitfall, `do_with`, the loop
    primitives (`repeat`, `repeat_until_value`, `do_until`,
    `do_for_each`, `keep_doing`), `when_all` tuples and `then_unpack`.
    Why this still matters: the hottest paths, where avoiding the
    coroutine frame pays (with a measurement), and reading existing code,
    including Seastar's own internals. Translating continuation code to
    coroutines, with before-and-after examples in the style of
    ScyllaDB's own conversion.
23. **HTTP** (18 pp). The `httpd` server: routes,
    handlers, errors, streaming JSON, and API definitions generated with
    `json2code`. That last one is how both ScyllaDB and Redpanda build
    their admin REST APIs. Also the HTTP client with retries. *Shoal v12.*
    *APIs:* `http_server`, `http_server_control`, `routes`, `matcher`,
    `function_handler` (`json_request_function`,
    `future_json_function`), `handler_base`, `file_handler` (static
    files), `const_req`, `http::request`, `http::reply` (status types,
    `write_body`), `operation_type`, the httpd exception family
    (`base_exception`, `bad_request_exception`, `bad_param_exception`,
    `not_found_exception`, `server_error_exception`,
    `redirect_exception`, `unexpected_status_error`),
    `json::json_return_type`, `json_void`, `stream_range_as_array`,
    `stream_object`, `json_element`/`json_list`/`json_chunked_list`,
    `json_base`, `json::formatter` and `date_time`, `path_description`,
    `api_docs` and `api_registry_builder20`; `http::client`, `retry_strategy`,
    `connection_factory`.
24. **Seastar RPC** (18 pp). Verbs, serialization, negotiation,
    compression, timeouts and cancellation, one-way messages, streaming,
    per-connection isolation. *Shoal v13: replication.*
    *APIs:* `rpc::protocol`, `client`/`server`, `client_options`,
    `client_info`, registering verbs (`register_handler`, `make_client`,
    `rpc_handler`, `signature`, `wait_type`), custom serializers
    (`read`/`write` overloads, `snd_buf`/`rcv_buf`), `rpc::optional`,
    `rpc::tuple`, `no_wait`/`no_wait_type`, `opt_time_point`,
    `cancellable`, the compressor factories (LZ4, LZ4 fragmented,
    `multi_algo_compressor_factory`), `sink` and `source`,
    `streaming_domain_type`, `closed_error`, `timeout_error`,
    `canceled_error`, `stream_closed`, `remote_verb_error`,
    `connection_id`.
### Part VII — From Development to Production

25. **Observability** (16 pp). Logging done right, metrics, and tracing.
    *Shoal v14.*
    *APIs:* `logger` (levels, `rate_limit`, `logger_registry`,
    `global_logger_registry`, `set_level`), `formattable`,
    `metrics::metric_groups`, `metric_definition`, `label` and
    `label_instance`, `description`, `make_counter`, `make_gauge`,
    `make_histogram` (and `metrics::histogram`), `make_summary`,
    `make_total_operations`, `make_total_bytes`, `make_current_bytes`,
    `make_queue_length`, `skip_when_empty`, aggregation labels,
    `double_registration`, relabeling (`relabel_config`,
    `metric_family_config`, `set_relabel_configs`), the new metric
    `collector`s, the Prometheus server and its filters, LTTng
    tracepoints.
26. **Testing** (18 pp). Shoal's test suite, plus integration tests
    with a real Redis client. Fixture tests (`SEASTAR_FIXTURE_TEST_CASE`,
    added to Seastar in August 2025 and already widely adopted in
    ScyllaDB) are a main topic, next to `SEASTAR_TEST_CASE` and
    `SEASTAR_THREAD_TEST_CASE`. **What the debug build does** (Nadav,
    2026-11-05: separate from debugging with gdb; it finds more bugs for
    you at development time, which is why projects run their tests in
    it). Checked in Seastar's CMakeLists.txt and sources: `need_preempt()`
    always true, so every `co_await` yields, even on a ready future;
    `then()` never runs a ready continuation inline; the ready-task queue
    is shuffled (`SEASTAR_SHUFFLE_TASK_QUEUE`); random-length bursts
    between I/O polls; the system allocator instead of Seastar's
    (`SEASTAR_DEFAULT_ALLOCATOR`, so memory isn't divided among shards)
    so that ASan works; ASan and UBSan; cross-shard checks
    (`SEASTAR_DEBUG_SHARED_PTR`: `shared_ptr`/`lw_shared_ptr` counts
    touched off their thread, `foreign_ptr` used off its owner shard;
    `SEASTAR_DEBUG_PROMISE`: promise made ready on the wrong shard;
    stale `smp_service_group`); guard pages under Seastar thread stacks
    and stack-clash protection (also in dev mode). Optional:
    `Seastar_TASK_BACKTRACE`, `Seastar_DEBUG_ALLOCATIONS`. Compares the
    modes: debug, sanitize (same checks, optimized), dev, release, fuzz.
    *APIs:* `SEASTAR_TEST_CASE`, `SEASTAR_THREAD_TEST_CASE`,
    `SEASTAR_FIXTURE_TEST_CASE` with `async_fixture`, `seastar_test`,
    `test_runner`/`global_test_runner` and `testing::entry_point` (for
    custom test mains), the `testing::exception_predicate` helpers
    (`message_contains`, `message_equals`),
    `scoped_no_abort_on_internal_error`, `SEASTAR_ASAN_ENABLED`,
    `manual_clock` tests, `tmp_dir`, `testing::random`, fault injection
    (and the error-injection pattern of both large projects), sanitizers
    and fuzzing; `perf_tests` (`PERF_TEST`, `PERF_TEST_F`,
    `do_not_optimize`, `start_measuring_time`/`stop_measuring_time`,
    `linux_perf_event`).
27. **Debugging and Profiling** (18 pp). Ignored exceptional futures,
    backtraces, `seastar-addr2line`. Stall reports. Hung futures: who is
    holding the gate? Watchdogs for stuck operations. **Debugging with
    gdb** as a major section (the debug build itself is in chapter 26):
    why ordinary backtraces say little in asynchronous code, the signals
    Seastar uses, core dumps of a program that owns all memory, and
    ScyllaDB's `scylla-gdb.py`, whose Seastar-general commands are taught
    on a stuck Shoal: `scylla fiber`, `tasks`, `task_histogram`,
    `task-queues`, `threads`/`thread`/`unthread`, `shard`, `smp-queues`,
    `memory`, `small-objects`, `large-objects`, `ptr`, `find`, `timers`,
    `io-queues`. The script is under ScyllaDB's source-available license:
    teach its use, never copy its code; check that it loads for a
    non-ScyllaDB binary. Then `perf`, flame graphs, the memory profiler.
28. **Deploying and Tuning** (16 pp). Hybrid CPUs (performance and
    efficiency cores): Seastar doesn't know core speeds (it places shards
    with `hwloc_distribute()` and ignores hwloc's CPU kinds), so find
    them with `lscpu -e` and run on the fast ones with `--cpuset`. The
    cloud variants of the same problem: vCPUs that share a physical core,
    and noisy neighbors. Reactor options: poll mode,
    `--overprovisioned`, and the backends (linux-aio, epoll, io_uring,
    asymmetric io_uring). cpusets, NUMA, hugepages, IRQ affinity and
    `perftune.py`, containers. Reactor statistics (uptime, busy time),
    `idle_cpu_handler` (`idle_cpu_handler_result`,
    `work_waiting_on_reactor`). Benchmarking Shoal against Redis and Valkey with
    `memtier_benchmark`, and interpreting the results.

### Part VIII — Seastar in the World

29. **Who Uses Seastar, and Why** (20 pp). The full history,
    expanding chapter 1's brief one: Cloudius Systems and OSv, the
    design decisions of the first years (with a passing mention of the
    EU MIKELANGELO project, which helped fund early Seastar work and its
    first tutorial), Seastar (2014) and ScyllaDB (2015), and how the API evolved, from continuations to coroutines
    and from API level 1 to 10. ScyllaDB in
    depth: why Seastar was written, and how its architecture maps onto
    Seastar (shard per core, the LSA cache, compaction and streaming
    schedulers, workload prioritization, shard-aware drivers, tablets).
    Redpanda in depth: the Kafka API, Raft per partition, why it chose
    Seastar, its fork and what it contributed back. Ceph Crimson.
    Others. How the project is maintained.
30. **Lessons from Large Seastar Code Bases** (18 pp). The idioms both
    ScyllaDB and Redpanda reinvented (the table in section 1b), each
    explained as a design: the problem, the shape of the solution,
    pitfalls. The code is our own, not copied. Then anti-patterns and
    war stories: stalls from huge vectors, cross-shard semaphore
    deadlocks, unbounded background work, exception storms.

### Back matter
- **Appendix A** — Building Seastar (`configure.py`, CMake, modes,
  cooking, Docker, C++ modules).
- **Appendix B** — Command-line option reference.
- **Appendix C** — API map: which header covers which topic, and which
  chapter explains it.
- **Appendix D** — RESP and Shoal's command reference.
- **Appendix E** — Glossary (shard, reactor, task, fiber, continuation,
  preemption point, stall, …).
- **Appendix F — The Seastar Toolbox.** A catalogue of the utility
  types and functions that real code uses constantly. Each also gets
  introduced in context the first time Shoal needs it:
  - `sstring` (`uninitialized_string`, `to_sstring`), `bool_class`,
    `noncopyable_function`, `optimized_optional`, `defer` and
    `deferred_action`.
  - `circular_buffer` and `circular_buffer_fixed_capacity`,
    `chunked_fifo`.
  - `visit` and `make_visitor`, `reference_wrapper`/`cref`, `lazy_eval`
    and `value_of`.
  - Byte order (`cpu_to_be`, `read_be`, `write_le`, `consume_be`, …),
    `unaligned`, `align_up`/`align_down`, `log2ceil`/`log2floor`,
    `bitsets::set_range`, `enum_hash`, `prefetch`, `cache_line_size`.
  - The `simple-stream` serialization helpers
    (`simple_memory_output_stream`, `simple_memory_input_stream`,
    `memory_output_stream`, `fragmented_memory_input_stream`,
    `measuring_output_stream`).
  - `sampler`, `shared_token_bucket`, `print_safe`, `pretty_type_name`,
    `indirect_equal_to` and the `shared_ptr` value hashers,
    `make_transform_iterator`, `tuple_map`, `count_leading_zeros` and
    `count_trailing_zeros`.
  - POSIX helpers (`file_desc`, `throw_system_error_on`,
    `throw_pthread_error`), useful when wrapping system calls Seastar
    does not cover.
- **Appendix G — C++ Corners at a Glance.** One paragraph per C++
  corner from the catalog in the C++ policy above, with a pointer to the
  chapter that explains it. It's the page to reread before a code
  review. (Proposed 2026-11-05.)
- **Colophon** — how the book was written by Claude Opus 5.5, edited by
  Nadav Har'El, drawing on Seastar's documents, its source code, its
  commit history and the applications built on it, and how it was
  typeset.
  It also notes that the book grew out of the original tutorial by
  Nadav Har'El and Avi Kivity.
- **Index.**

## 5. Deliberately left out or only mentioned

**Experimental features are left out** unless they are important for
the exposition (Nadav, 2026-11-05). Today that means everything in a
`seastar::experimental` or `seastar::coroutine::experimental`
namespace:
- `experimental::websocket`. Redis doesn't use WebSocket, so Shoal has
  no use for it either.
- `coroutine::experimental::generator` (one use in ScyllaDB).
- `experimental::fsnotify`.

When the audit is rerun, an experimental name counts as deliberately
omitted, not as a gap. If a feature graduates while we write (as the
process API did), it becomes a candidate again.

- **Only in "Continuations" or as a historical note:** `distributed<>`,
  `later()`, variadic futures, the `io_priority_class` API, direct
  `semaphore::wait()`/`signal()`, and `keep_doing` (unused in ScyllaDB).
- **Removed or deprecated, so omitted:** scollectd, `reactor::at_exit`,
  `scattered_message`, `smp::count` (now `smp::shard_count()`), the
  ostream formatters (now `{fmt}`), `compat::source_location` (now
  `std::source_location`), `packet_data_source`, and
  `vector_data_sink`.
- **One section, not a chapter:** the native TCP stack and DPDK
  (`net::interface`, `device`, `packet`, `ipv4`), which are rare in
  production.
- **Internals:** `fair_queue` and `shared_token_bucket` appear only in
  the I/O scheduler chapter's "how it works" box. `task`, `make_task`
  and `schedule` appear only in chapter 5's explanation of the reactor.
- **Only in Redpanda's fork, not upstream:** `chunked_vector`,
  `chunked_hash_map` and the sampling CPU profiler. We mention them
  only to motivate chapters 19 and 27.

## 6. How we will work

- **One chapter at a time**, each followed by a stop for Nadav's
  review. For each chapter, I write the Shoal version first, build it,
  test it against `redis-cli` (and Valkey where relevant), and only
  then write the prose around real snippets.
- **The book tools** (filters and the build script) get built during
  chapters 1–3, so the first review already comes as PDF, HTML and
  text.
- **C++23 is a promise.** The Preface says everything in the book works
  with C++23, while Seastar's own build defaults to the newest standard
  the compiler supports (C++26 today). So every Shoal version and every
  code snippet must also be built with C++23 (`--c++-standard=23`, or
  `CMAKE_CXX_STANDARD=23`), not only with the default; before the book is
  final, build Seastar itself and all Shoal versions with C++23 once more.
  Chapter 1's snippets were checked with both `-std=c++23` and
  `-std=c++26` (2026-11-05).
- **Chapter order and references.** The order lives only in
  `metadata.yaml`; chapter files are named by subject, and the text refers
  to chapters by label (`[chapter](#ch:stalls)`), never by number (see
  README.md). The chapter numbers in this plan are for discussion only.
- **Recent-usage check:** `research/recent_usage.py` counts Seastar
  APIs in last year's ScyllaDB commits (`research/recent_usage.md`).
  Every rising API must get real coverage, not just a mention; rerun it
  when the book is close to final.
- **Before the book is final**, I rerun the coverage audit against the
  chapters themselves and fix any gaps.
- **Learning from ScyllaDB and Redpanda.** I study both, ScyllaDB most
  heavily, but never copy code from either. Every snippet is written
  for Shoal or for the book.

## 7. Questions for Nadav, all answered (2026-11-05)

1. ~~**Format:** Is Pandoc Markdown with LuaLaTeX for the PDF acceptable?~~
   Accepted. Nadav installed the packages on 2026-11-05; see section 2.
   Fonts (Libertinus Serif, Source Code Pro) and the remaining LaTeX
   packages are installed too; see README.md.
2. ~~**Application:**~~ Decided: the Redis protocol, with values on disk
   (Bitcask), named Shoal; see section 3.
3. ~~**Where things live.**~~ Decided (2026-11-05): the book goes in
   Seastar's `doc/book/`; Shoal gets its own git repository,
   `github.com/nyh/shoal` (not under scylladb for now), with one tag
   per version, while we write. Nadav expects that in the end
   Seastar will want copies of the tagged versions' contents inside
   its own tree rather than a separate repository. We will reconsider
   then; the include filter supports both. Original suggestion: the book source goes in the
   Seastar repo under `doc/book/`, replacing `tutorial.md` in the
   "Fixes #916" patch. Shoal goes in its own repository (for example
   `nyh/shoal`, or later under scylladb) with linear history and tags,
   and the book build fetches snippets by tag. Upstream Seastar
   probably won't want 15 tagged versions or a submodule. The
   alternative is to put the final Shoal in Seastar's `demos/` and keep
   only the history elsewhere.
4. ~~**The survey of users:**~~ Decided (2026-11-05): a teaser in
   chapter 1 and the full survey in chapter 29. The teaser stresses that
   Seastar comes from ScyllaDB and its needs (Nadav).
5. ~~**Namespace convention in snippets:**~~ Decided (2026-11-05):
   unqualified names, as in ScyllaDB (`using namespace seastar;` in
   `seastarx.hh`) and in Seastar's own `apps/` and `demos/`. An API's
   first mention in the text gives its full name (`seastar::sharded`),
   and the index lists full names. Chapter 3 compares the three
   conventions: full `seastar::`, unqualified, and Redpanda's
   `namespace ss = seastar;` with `ss::` (about 42,400 uses there,
   against about 1,100 of `seastar::`). It explains the clashes with
   `std` (`shared_ptr`, `make_shared`, `future`, `promise`), and Shoal
   gets a small `seastarx.hh`-style header that resolves them with
   `using seastar::shared_ptr;` and the like, as ScyllaDB does.
6. ~~**Scope:**~~ Decided (2026-11-05): keep all 29 chapters and about
   440 pages, with no merges for now. We may reconsider merging chapter
   17 into 16, or chapter 30 into 28, later. WebSocket is dropped (see
   section 5).
7. ~~**Exercises at the end of each chapter:**~~ Decided (2026-11-05):
   yes, in the spirit of Kernighan and Pike's *The Unix Programming
   Environment* (Nadav did those). Two to five per chapter, short and
   concrete, mostly extending the current Shoal version ("add `INCR`",
   "make `KEYS` not stall"). As in that book, some exercises are
   answered later by the text itself, when Shoal grows the same feature.
   We won't publish a full solutions set for now.
8. ~~**The book's own license.**~~ Decided (2026-11-05): deferred. An
   unpublished draft needs no license; the choice matters only when the
   book is merged into Seastar or published elsewhere. If professional
   publication is a real prospect by then, talk to a publisher and to
   ScyllaDB (the likely copyright holder) first. Publishers prefer
   non-commercial licenses (*Pro Git*, *Automate the Boring Stuff*),
   though O'Reilly has published CC BY and CC BY-SA books. Otherwise use
   Apache 2.0, like the rest of Seastar. Loosening a license later is
   easy, but tightening one is not, and outside contributions under
   Apache 2.0 would make it impossible. Publishers may also care about
   AI authorship, which the colophon discloses. Until then, the book says
   nothing about its license (Nadav). Shoal's code is Apache 2.0.
9. ~~History facts~~ Answered by Nadav; recorded in section 8.

## 8. History notes for chapters 1 and 29

From Nadav (2026-11-05):
- **Name Avi Kivity in the book**, explicitly, as Seastar's creator:
  in chapter 1's brief history, in chapter 29's full history, and in
  the Colophon's acknowledgment of the work the book draws on. Give
  his background (KVM's original lead developer, then co-founder of
  Cloudius Systems/ScyllaDB) and his motivation for writing Seastar.
- **Open source from the start.** Seastar was open source from its
  first commit, but almost nobody knew about it until ScyllaDB, which
  used it, was released.
- **The name** is a pun: "Seastar" sounds like "C*", i.e. "C star",
  the common shorthand for Cassandra.
- **Motivation.** Avi Kivity wrote Seastar after noticing how badly
  Cassandra performed because of its architectural limits: many
  threads, blocking system calls and shared memory. Seastar's answer
  is a thread per core, non-blocking asynchronous code, and memory
  sharded between cores.

- **MIKELANGELO.** The EU Horizon 2020 research project MIKELANGELO
  (CORDIS grant 645402) helped fund the young company, still called
  Cloudius Systems, and its work on Seastar. That includes Seastar's
  first tutorial, the ancestor of this book. Mention it **once, in
  passing**, in chapter 29's history: a sentence or an aside, not an
  official acknowledgment (Nadav's preference).

From the repository and web sources (to verify further when writing):
- MIKELANGELO facts from sources:
  - A three-year Horizon 2020 project with nine industrial and
    academic partners, ScyllaDB among them.
  - Its goal: a lean virtualization stack (OSv, "sKVM") for cloud
    and HPC.
  - The final CORDIS report lists the Seastar work done in it:
    improved RPC, I/O scheduling, iotune, CPU scheduling, monitoring,
    ext4 support, a log-structured memory allocator, and DPDK
    support.
  - Sources: https://www.scylladb.com/2016/03/08/project-mikelangelo
    and https://www.cordis.europa.eu/project/id/645402/reporting
    (check the project's dates and deliverables, including the
    tutorial, in its reports).
- Avi Kivity's first commit ("Initial commit") is dated 2014-08-10.
  The `NOTICE` file says "Copyright 2015 Cloudius Systems".
- Dor Laor (co-founder) has said the name is a play on C*. Laor and
  Kivity met in 2005 at a startup that was later acquired by Red Hat
  (Qumranet, the origin of KVM; Kivity was KVM's original lead
  developer). Cloudius Systems was founded in 2012, made OSv, and
  became ScyllaDB in 2015. ScyllaDB was announced in September 2015.
- **Resolved while writing chapter 1** (confirmed by Nadav, who asked for the exact dates in the text):
  ScyllaDB's blog has a post dated 2015-02-20 announcing Seastar (Apache
  2.0, "on OSv and Linux", memcached benchmarks), so Seastar was
  publicly announced seven months before ScyllaDB launched on
  2015-09-22. The rename to ScyllaDB was announced with that launch
  (eWeek, 2015-09-22). Chapter 1 says: open source from the first
  commit, announced in February 2015, but few people outside the
  company paid attention until ScyllaDB launched.
- Earlier note: some sources suggest Seastar was publicly visible
  before ScyllaDB's launch. ScyllaDB's blog has a post dated 2015-04-20
  about a Seastar meetup, possibly backdated from an older blog, and
  there are "Cloudius Systems presents: Seastar" slides. Wikipedia's
  date for the rename also conflicts with the other sources.
- Sources so far:
  - https://en.wikipedia.org/wiki/Avi_Kivity
  - https://scylladb.com/2023/12/13/codestory (podcast with Dor Laor)
  - https://eweek.com/database/scylladb-database-emerges-out-of-cloudius-systems
  - https://www.scylladb.com/2015/04/20/seastar-meetup/
  - https://www.slideshare.net/slideshow/seastar-sfba-cug/61291453
  - https://www.scylladb.com/2024/02/14/seastar-scylladb-and-c23/
  - https://www.scylladb.com/2021/05/13/an-interview-with-pekka-enberg-modern-hardware-old-apis
- More material to search for when writing: Avi Kivity's talks and
  blog posts (for example "Back to the Future with C++ and Seastar"),
  the Seastar Summit keynotes (2019 onwards), and Redpanda's own
  account of why it chose Seastar.
