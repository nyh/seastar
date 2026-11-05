# The Case for Seastar {#ch:case-for-seastar}

Open the case of a server bought today, and count what is inside. Two
processor sockets, each holding a hundred or more cores. A row of NVMe
drives, each able to perform a few million random reads per second. A
network card that moves 100 or even 400 gigabits per second. Hundreds of
gigabytes of memory, or several terabytes.

Now run a typical server program on it (a database, a message queue, a
cache) and watch what it does with all that hardware. Usually, not
much. One core is busy and the rest idle, or all cores are busy but most
of their time goes to waiting for locks and to moving data between their
caches. The disks are nowhere near their limit, because the program can't
issue requests fast enough to keep them busy. Adding cores makes things
only a little faster, and sometimes slower.

This is not because the people who wrote these programs were careless.
It is because the programs were designed for different machines, with a
few cores, spinning disks and slow networks, and because the obvious way
of writing a server, the way most of us were taught, stops scaling long
before it reaches a hundred cores.

Seastar is a C++ library for writing server applications that use the
whole machine. Programs written with Seastar routinely keep every core
busy doing useful work, drive NVMe drives and fast network cards close to
their limits, and keep latency low and predictable while doing it. This
book teaches you how to write such programs.

This first chapter explains why Seastar exists. We look at what changed
in the hardware, at what it costs to share data between cores, and at
how the design of servers evolved to cope. Then we see what Seastar
offers in answer, how it compares with other asynchronous frameworks you
may know, why it is written in C++, and what it asks of you in return.
The chapter ends
with a short history of Seastar, its license, the programs people have
built with it, and an introduction to the program we will build
together in this book.

## The machine has changed

For decades, programmers got faster software for free. Every year or
two, processors ran at a higher clock rate, and the same program, without
any change, ran faster. Around 2005, that stopped. Clock rates leveled
off at a few gigahertz, because faster chips would consume too much power
and produce too much heat. Herb Sutter summarized the consequences in a
famous article titled "The Free Lunch Is Over":[^sutter] chip makers would
keep adding transistors, but they would spend them on more cores rather
than faster ones. Programs that wanted to run faster would have to learn
to use many cores at once.

[^sutter]: Herb Sutter, "The Free Lunch Is Over: A Fundamental Turn
    Toward Concurrency in Software", *Dr. Dobb's Journal*, March 2005.

Twenty years later, the prediction has come true beyond what most people
expected. A single server processor has more than a hundred cores, and a
two-socket server has several hundred. Each core is not much faster than
a core from 2005, but there are a hundred times more of them.

Storage changed even more dramatically. A spinning hard disk performs
roughly a hundred to two hundred random reads per second, because each
read waits for a mechanical arm to move and for the platter to rotate.
Software written for such disks could afford to be slow. Whatever the
program did, the disk was slower. A modern NVMe drive has no moving
parts, and it can perform millions of random reads per second, with each
read taking tens of microseconds. That is ten thousand times more than
the disk it replaced. The disk is no longer the bottleneck; now the
software that drives it is.

Networks followed the same path. Server network cards went from one
gigabit per second to ten, then to a hundred, and now to four hundred.
At these speeds, a single connection can deliver millions of small
requests per second to a server, more than one core could process even
if it did nothing else.

Let's put these numbers together, and see what they mean for a
program. Suppose we want a server to answer a million small requests per
second on each core. A core running at 3 GHz performs three billion
cycles per second, so each request gets a budget of 3,000 cycles, which
is one microsecond. Here is roughly what some common operations cost on
such a machine:

| Operation | Approximate cost |
|---|---|
| Reading a value from the core's own L1 cache | 1 ns |
| An atomic increment of a variable no other core touches | 5 to 10 ns |
| Reading memory that isn't in any cache | 100 ns |
| Moving a cache line that another core just wrote | 50 to 200 ns |
| A simple system call | 100 ns to 1 µs |
| A context switch between two threads | 1 to 5 µs, plus the cache damage |

These are orders of magnitude, not precise figures; the exact numbers
depend on the processor, and you can measure some of them yourself in
the exercises at the end of this chapter. But the conclusion is clear.
In a budget of one microsecond per request, we can afford a few cache
misses and perhaps one system call. We can't afford a context switch,
and we can't afford to fight with other cores over shared data, even
once per request.

## What sharing costs

Most server programs share data between cores without thinking about it.
A cache of recently used items, a table of open connections, a counter
of requests served, a pool of memory buffers: in a typical
multithreaded server, every thread may touch any of these at any time.
The program protects them with locks, or uses atomic operations to
update them safely. On a machine with four cores, this works well
enough. On a machine with a hundred, it falls apart, for several
reasons.

**Locks serialize.** While one thread holds a lock, every other thread
that needs the lock waits. If each request holds a global lock for even
one percent of its processing time, the program can never use more than a
hundred cores' worth of processing, no matter how many cores it has.
In practice, contention appears long before this theoretical limit,
because waiting threads add overhead of their own: they spin and waste
cycles, or they sleep, and then they pay for context switches.

**Atomic operations are not free.** It's a common belief that lock-free
code, which uses atomic instructions instead of locks, solves the
problem. It doesn't. An atomic operation must take exclusive ownership of
the cache line holding its variable. If another core used that variable
recently, the cache line must first travel from the other core's cache
to ours. This is called *cache-line bouncing*. A counter incremented by
every core on every request bounces from cache to cache all the time,
and each increment costs a hundred nanoseconds or more instead of a
few. Worse, the hardware performs these transfers one at a time, so a
heavily used shared variable becomes a lock in disguise.

**Sharing can be accidental.** Two unrelated variables that happen to sit
in the same 64-byte cache line bounce together, as if they were one
variable. This *false sharing* can turn two independent counters, each
used by a different core, into a bottleneck. It is notoriously hard to
find, because nothing in the source code reveals it.

**Memory is not uniform.** In a two-socket server, each processor has
its own memory. A core can read memory attached to the other socket, but
more slowly and through a link that all the cores share. A program that
lets any thread work on any data will constantly reach across this link.

**Context switches are expensive.** When a thread blocks, waiting for a
lock, for the disk or for the network, the kernel switches the core to
another thread. The switch itself costs a few microseconds. Then the new
thread runs with a cold cache, because the previous thread filled the
cache with its own data. A program with many more threads than cores
pays this price constantly.

The fix for all of these problems is the same: don't share. If each core
has its own data, which no other core reads or writes, then there are no
locks to wait for, no atomic operations, no bouncing cache lines and no
false sharing. Each core can keep its data in memory attached to its own
socket. And if a core never needs to wait for another core, it never
needs more than one thread. This idea is the foundation of Seastar.

## How servers evolved

For most of the history of server software, programmers had to choose
between two kinds of servers: ones that were easy to write but
inefficient, and ones that were efficient but hard to write. Seastar's
goal is to get the best of both worlds, and to see what that means, we
need to look at how the two kinds came to be.

The first network servers, such as the classic `inetd`, Sendmail and the
Apache web server, used a separate operating-system process, and later a
thread, for each connection. Such a thread reads a request, maybe reads a
file from disk, writes a reply, and waits for the next request. Its code
is simple and linear, just like an ordinary program, and when it needs to
wait, for a slow client or for the disk, it simply blocks while the
kernel runs other threads. This style of programming is called
*synchronous*: each operation completes before the next one starts. It
is easy to write, but every thread needs memory for its stack, and every
switch between threads costs time. In 1999, Dan Kegel posed the "C10K
problem": how can a single server handle ten thousand connections at
once, when most of them are idle or slow? Ten thousand threads were too
many.

The answer, popular during the following decade, was the
*event-driven* server. Instead of a thread per connection, the server
has a single thread, which runs a loop. In each iteration, the loop asks
the kernel (using `select()`, `poll()` or the faster `epoll`) which of
the many open connections have something to do: a new request has
arrived, or there is room to send more of a reply. The server handles
each such event without blocking, and goes back to the loop. The nginx
web server, Node.js and Redis all work this way. Because the operations
don't wait for each other to complete, this style of programming is
called *asynchronous*.

The event-driven design solved the C10K problem: it is efficient. But it
has two problems of its own. The first is that it is hard to program.
Code that used to be a simple sequence of steps becomes a collection of
small callback functions and a state machine that remembers where each
connection is in its processing. Simple servers stay manageable. A
complex server, such as a database, becomes a maze, and so the authors
of complex servers mostly stayed with the synchronous design and its
inefficiency. The second problem is that a single thread uses a single
core. Redis famously executes all its commands on
a single thread: a busy Redis server keeps one core at 100% while the
rest of the machine watches.

The usual fix for the second problem is to run several event loops, one
per core, all serving the same data. But then the cores share that data
again, and the locks, atomic operations and bouncing cache lines come
back. Another common compromise keeps some blocking code, typically for
disk access, and adds a pool of threads to run it. The Apache Cassandra
database, for example, is mostly asynchronous, but it read its data
files through memory-mapped I/O, and accessing a memory-mapped file
blocks the whole thread whenever the data isn't in memory. So Cassandra
had to run many threads per core, and paid for the context switches.

The next step, and the one Seastar takes, is to combine the event loop
with a strict rule against sharing. The program runs exactly one thread
on each core, and it divides its data between the cores. This design is
called *shard-per-core* or *thread-per-core*, and each core with its
part of the data is called a *shard*. Each shard serves requests only
for its own data, without locks and without atomic operations. When a
shard needs something that belongs to another shard, it doesn't reach
into the other shard's memory. It sends the other shard a message, and
continues with other work until the answer arrives.

Shard-per-core removes the cost of sharing, but it makes the first
problem of event-driven programming, the difficulty, even worse. Now
the program must be asynchronous not only when it talks to the network
and to the disk, but also when it talks to its own other shards. Without
help, such a program would be unbearably hard to write. Providing that
help, so that a program as complex as a database can be written in the
efficient design, is what Seastar is for. The difference between
Cassandra and ScyllaDB, which implement the same database, is exactly
this difference in design.

## What Seastar gives you

Seastar is a library, not a language or a runtime. You write an ordinary
C++ program, link it with Seastar, and Seastar takes over the machine:
it starts one thread on each core, and runs your code on them. Here is
what you get.

**Share-nothing shards.** Each shard has its own thread, pinned to its
own core, and its own part of the machine's memory. Seastar's memory
allocator is per shard, too, so allocating memory never takes a lock, and
memory allocated on a shard comes from memory attached to that shard's
own socket. Shards communicate by passing messages through lock-free
queues, one queue for each pair of shards, so that even the
communication involves no contended shared variables.

**Every shard is the same.** Many multithreaded servers divide their
work by function: some threads accept connections, others read from the
network, a pool of threads reads from the disk, and yet another pool
does the actual processing. Each request travels between these threads,
and each kind of thread can become the bottleneck when the load shifts.
In Seastar, all shards are alike. No thread specializes in networking
or in disk access, and no request is handed from one thread to another:
each shard accepts connections of its own, parses their requests, runs the
application's logic and performs its own disk I/O, all for the part of
the data it owns. A server with twice as many cores simply has twice as
many identical shards.

**A cooperative scheduler.** On each shard, Seastar runs its own
scheduler, called the *reactor*. Instead of threads, the reactor runs
small *tasks*, each of which runs until it finishes a piece of work and
then gives up the core. A task never blocks: when it needs to wait for
something, it arranges to continue later and returns. Switching between
tasks is a function call, not a context switch, so a shard can juggle
hundreds of thousands of concurrent operations, which would need
hundreds of thousands of threads in a synchronous server.

**Futures and coroutines.** Seastar represents any operation that may
not finish immediately, whether it reads from the network, writes to the disk, sleeps,
asks another shard for an answer or even performs a long computation, as
a *future*. Because all of these look the same, they can be combined at will: a
single function can receive a request, start several disk reads and
requests to other shards in parallel, wait for all of them and send the
reply. With C++20 coroutines, you
can write such asynchronous code so that it reads almost like
synchronous code. Here, for example, is a sketch of a function that
serves a single client connection, reading requests and writing replies
until the client disconnects:

```cpp
future<> handle_connection(connected_socket s) {
    auto in = s.input();
    auto out = s.output();
    while (auto request = co_await read_request(in)) {
        co_await out.write(co_await execute(*request));
        co_await out.flush();
    }
    co_await out.close();
}
```

Each `co_await` marks a point where the function may have to wait: for
the next request to arrive, for its execution to complete, or for the
reply to be sent. While it waits, the shard serves other connections.
Yet the code reads from top to bottom, without callbacks or state
machines. You will write a function very much like this one in
[chapter](#ch:coroutines). (`read_request()` and `execute()` are functions of our own;
you'll see those, too.)

**Asynchronous everything.** Every I/O operation in Seastar is
asynchronous, including disk I/O, which most frameworks leave blocking.
Seastar reads and writes files with direct I/O, bypassing the kernel's
page cache. This lets the program control its own caching, and lets
Seastar keep many disk requests in flight at once, which is what NVMe
drives need to reach their full speed.

**Message passing between shards.** When a shard needs data that another
shard owns, it doesn't lock the data and fetch it. Instead, it asks the
owning shard to do the work, and waits for the result. Avi Kivity,
Seastar's creator, sums this up as moving the operations to the data,
rather than the data to the operations. Seastar makes it easy to run code on another shard
and get back its result as a future. On top of this, it
provides *sharded services*: an object with one instance on each shard,
which you can address as a whole. For example, if a key-value store
keeps a part of the keys on each shard, counting all the keys is a
single call that asks every shard to count its own keys, and adds up
the results:

```cpp
future<size_t> count_keys(sharded<store>& db) {
    return db.map_reduce0([] (const store& s) { return s.size(); },
                          size_t(0), std::plus<>());
}
```

**Schedulers for CPU and I/O.** A real server does many things at once:
it serves user requests, but it also compacts files, replicates data
and repairs inconsistencies in the background. When background work
competes with user requests, latency suffers. Seastar's CPU scheduler
divides each core's time between *scheduling groups* in proportions you
choose, and its I/O scheduler does the same for each disk. Both keep
latency predictable even when the machine is fully loaded, which is
often more important than raw speed.

**A toolbox for servers.** Seastar includes TCP and TLS networking (with
an optional user-space network stack that bypasses the kernel), an HTTP
server and client, an RPC framework for communication between servers,
metrics that Prometheus can collect, logging, timers, semaphores and
other coordination primitives, and a framework for testing asynchronous
code. Most of the infrastructure a server needs is already there.

## Seastar and other asynchronous frameworks

When Seastar was born, asynchronous programming was a niche skill. It
isn't anymore. Node.js runs JavaScript on an event loop; Python, C# and
Rust have `async` and `await`; Go runs millions of lightweight
goroutines on a few operating-system threads; Java 21 added virtual
threads. If you have used any of these, much of Seastar will look
familiar: Seastar's futures and coroutines play the same role as
promises and `async` functions in these languages, and its reactor is an
event loop much like Node's.

The difference lies in what these frameworks assume about the machine.
Go, Rust's popular Tokio runtime and Java's virtual threads run their
tasks on a pool of threads, typically one per core, but a task is not
bound to a core: when one thread runs out of work, it *steals* tasks from
the others. This balances the load automatically, but it means any task
can run on any core, so the data that tasks use must be safe to share
between cores, with locks, atomic reference counts and all the costs
described above. Node.js avoids sharing by running a single thread, and
so uses a single core; to use more, you run several independent
processes.

Seastar makes the opposite trade-off. A task never migrates: it runs on
the shard that created it, next to its data, and when it needs data that
another shard owns, it sends the work to that shard rather than fetching
the data. Load is balanced not by moving tasks around, but by how the
program divides its data and its connections between the shards. This
is a design decision you make deliberately, and this book discusses it
in depth.

| | Typical asynchronous framework | Seastar |
|---|---|---|
| Threads | a pool, shared by all tasks | one per core, each running its own shard |
| Tasks | migrate between threads | stay on the shard that created them |
| Data | shared, protected by locks and atomics | owned by one shard, reached by messages |
| Memory allocator | shared, with per-thread caches | separate for each shard |
| Disk I/O | blocking calls in a helper thread pool | asynchronous, from the shard itself |
| CPU and I/O isolation | none, or operating-system priorities | scheduling groups, and an I/O scheduler |

Seastar's approach has since been adopted by others. In 2020, Glauber
Costa, who had worked on Seastar for years, released Glommio, a
thread-per-core runtime for Rust based on the same ideas, and Dragonfly,
a Redis-compatible store, divides its data between threads that share
nothing. But Seastar remains the most mature and complete framework of
its kind, and it has been running production databases since 2015.

## Why C++

Seastar is written in C++, and so are the programs that use it. This was
a deliberate choice, made for the same reason as everything else in
Seastar: performance.

Many popular server languages, such as Java, Go and JavaScript, manage
memory with a garbage collector. A garbage collector is convenient, but
it runs when it decides to, and it can pause the program or steal its
CPU time at unpredictable moments. A server that must answer every
request within a millisecond cannot afford such pauses; operators of
large Cassandra clusters, for example, spend much effort tuning the Java
garbage collector to keep its pauses short. C++ has no garbage
collector. The program decides exactly when memory is allocated and
freed, and Seastar provides its own fast, per-shard memory allocator.

C++ also gives the programmer full control over how data is laid out in
memory, which matters when every cache miss counts, and it compiles to
native code with no interpreter or virtual machine in between. Most
importantly for Seastar, C++ lets libraries build powerful abstractions
that cost nothing at run time. Seastar's futures, its message passing
between shards and many of its utilities are templates, which the
compiler specializes for each use and optimizes together with your code.
C++20 coroutines are compiled into ordinary functions and a small object
holding their state, with no runtime system behind them.

The price of this is paid at compile time. Seastar's headers are heavy
with templates, and compiling a large Seastar program takes a long time
and much memory: the developers of ScyllaDB have invested considerable
effort in keeping their build times bearable. C++ compiler error
messages, especially for templates, can also be long and puzzling. This
book helps with the second problem, and [chapter](#ch:getting-started) shows how C++ modules
can help with the first.

## What Seastar asks in return

Seastar is not free. It asks you to accept some rules, and it's only
fair to state them before you invest your time in learning it.

**Never block.** Each shard has a single thread. If your code blocks it,
by calling a blocking system call, waiting on an ordinary mutex, or
running a long loop without pause, the entire shard stops: every
connection, every timer and every background task on that core waits for
you. Seastar provides non-blocking alternatives for everything a server
normally needs, and it can detect and report code that runs too long
without giving up the core. But you have to learn the discipline, and
any library you use must follow it, too. A library that blocks, such as
a typical database client or a compression library working on huge
buffers, needs special treatment, which we cover in [chapter](#ch:threads).

**C++.** Seastar uses modern C++ intensively: templates, lambdas, move
semantics and coroutines. This book assumes you know C++, and teaches
the less familiar parts as they come up. But if your team writes Go,
Java or Python, Seastar is not for you, though its ideas can still guide
you.

**Linux.** Seastar runs only on Linux. It relies on Linux's asynchronous
I/O interfaces, and on Linux's ways to pin threads to cores and control
memory.

**The machine is yours.** By default, Seastar assumes it owns the
machine: it starts a thread on every core and takes almost all the
memory. You can tell it to use fewer cores and less memory, and many
deployments do. But Seastar shines when it doesn't compete with other
programs for the same cores, and a shard-per-core program is a poor
neighbor on a machine shared with many other busy processes.

**Time to learn.** Asynchronous programming is harder than synchronous
programming, even with coroutines. You need to think about the lifetime
of objects while operations are in flight, about which shard owns which
data, and about what happens when an operation fails halfway. This book
exists because these skills take time to learn.

So Seastar is not the right tool for every program. If your server
handles a few hundred requests per second, or spends most of its time
waiting for another service to answer, the simplest design will serve
you better. Seastar is for programs where performance is the product:
databases, storage systems, message queues, caches and network services
that must squeeze everything out of the hardware and keep their latency
low while doing it.

## A brief history

Seastar was created by Avi Kivity. Before Seastar, Kivity was the
original lead developer of KVM, the virtualization technology built into
the Linux kernel, which he started in 2006 at an Israeli startup called
Qumranet. Red Hat acquired Qumranet in 2008, and Kivity continued to lead
KVM there. In late 2012 he left Red Hat and, together with Dor Laor,
founded a new company, Cloudius Systems.

Cloudius's first product was OSv,[^osv] an operating system designed for
running a single application in a virtual machine in the cloud,
announced in September 2013. OSv was written in C++, and it ran
existing Linux applications, some of them faster than Linux itself. But
the team kept running into the same wall: in many applications, the
operating system was not what held performance back. The applications'
own architecture was. Apache Cassandra was a prominent example. Its
architecture, with many threads, blocking system calls and data shared
between threads, kept it from using more than a fraction of a modern
server, and no operating system could change that.

[^osv]: OSv is still available as an open-source project, at
    <https://github.com/cloudius-systems/osv>.

So Kivity set out to build a framework that would let applications use
the hardware fully: a thread per core instead of many threads,
non-blocking asynchronous code instead of blocking system calls, and
memory divided between the cores instead of shared. His first commit to
Seastar is dated August 10, 2014. The name is a pun: "Seastar" sounds
like "C\*", read "C star", a common shorthand for Cassandra.

Seastar was open source from its very first commit. Cloudius announced
it publicly on February 20, 2015, with benchmarks of a
memcached-compatible server built on it, but at the time few people
outside the company paid attention. That changed on September 22, 2015,
when Cloudius released the program that Seastar had been built for:
ScyllaDB, a reimplementation of Cassandra in C++ on top of Seastar,
compatible with Cassandra's protocol and data files. The launch claimed
one million operations per second on a single server, many times what
Cassandra achieved on the same hardware. The company renamed itself
ScyllaDB, and it has developed Seastar together with ScyllaDB ever since.

Others followed. In 2019, Alexander Gallego founded Vectorized, later
renamed Redpanda Data, to build Redpanda, a Kafka-compatible streaming
platform written in C++ on Seastar. Ceph, the open-source distributed
storage system, began Crimson, a new implementation of its storage
server built on Seastar. Today Seastar is developed on GitHub,[^github] by
engineers from several companies. Avi Kivity still leads the project:
he and Pavel Emelyanov merge most changes. In the twelve months before
this writing, 67 people contributed about 800 changes, and about three
quarters of those came from ScyllaDB and Redpanda. Altogether, about
250 people have contributed to Seastar since 2014. The most prolific of
them, each of whom contributed thousands of lines of changes to Seastar
over a period of years, are Rafael Ávila de Espíndola, Raphael S. Carvalho, Kefu
Chai, Glauber Costa, Botond Dénes, Stephan Dollberg, Travis Downs, Paweł
Dziepak, Pavel Emelyanov, Tomasz Grabiec, Jesse Haber-Kucharsky, Benny
Halevy, Nadav Har'El, Asias He, Amnon Heiman, Avi Kivity, Gleb Natapov,
Calle Wilund and Vlad Zolotarov.
[Chapter](#ch:who-uses-seastar) tells the fuller story.

[^github]: <https://github.com/scylladb/seastar>

## The license

Seastar is distributed under the Apache License, version 2.0. In
practice, this means you can use it to build any software you like,
open source or proprietary, and you can modify Seastar itself, provided
you keep its copyright and license notices. The license also includes a
patent grant: contributors license any of their patents that their
contributions use, so you don't need to worry about being sued over
using Seastar's code by the people who wrote it.

Seastar's `NOTICE` file lists the few parts that came from elsewhere:
some code from OSv and from the DPDK project, both under the BSD license,
and one file from the Android Open Source Project, under the Apache
license.

The license of Seastar is independent of the licenses of the programs
built with it. ScyllaDB and Redpanda have each changed the licenses of
their own products over the years, but Seastar itself has remained under
the Apache license throughout, and it's what both of them build on.

## What people have built

The best evidence for Seastar's approach is the software built on it.
Here is a short preview; [chapter](#ch:who-uses-seastar) surveys the users of Seastar in
detail.

**ScyllaDB** is where Seastar comes from. Seastar was created to make
ScyllaDB possible, and ScyllaDB remains its largest user and the main
force behind its development; many of Seastar's features, including its
I/O scheduler and scheduling groups, were born from ScyllaDB's needs.
ScyllaDB is a distributed database compatible with Apache Cassandra and
with Amazon DynamoDB, and its developers claim that a cluster of
ScyllaDB servers can do the work of a Cassandra cluster many times its
size. It is also one of the largest Seastar programs, with about half a
million lines of C++ (over 700,000 counting its tests), and much of what
this book teaches about writing large Seastar programs comes from
studying it.

**Redpanda** is a streaming data platform compatible with Apache Kafka.
Where Kafka is written in Java and Scala, Redpanda is written in C++ on
Seastar, and its developers credit much of its speed to the techniques
this book teaches: a thread per core, direct I/O to the disk, and no
sharing between cores. After ScyllaDB, Redpanda is the largest
contributor to Seastar.

**Crimson** is a new implementation of the storage server (the "OSD") of
Ceph, the widely used open-source storage system. Crimson is built on
Seastar, together with SeaStore, a new storage backend designed for
fast NVMe drives. In Ceph's 2025 release, both were still technology
previews, not yet ready for production use.

There are also smaller projects, including an RPC framework, a web
framework and a Cassandra driver built on Seastar, and many programs
built inside companies that we will never see.

## Meet Shoal

Like the classic programming books that inspired it, this book is built
around a single program, which grows from chapter to chapter. Each new
Seastar feature is introduced when the program needs it, so you see not
only how each feature works, but also why you would want it.

Our program is called **Shoal**. It is a key-value store that speaks the
protocol of Redis, which means that the existing Redis tools, client
libraries and benchmarks all work with it. You can type commands at it
with `valkey-cli` from the very first version, and measure it against a
real Redis-compatible server at any point along the way.

Shoal starts small: in [chapter](#ch:coroutines) it is a single-shard server that stores
strings in memory and understands half a dozen commands. Then it grows.
It learns to handle many requests at once, to expire keys, to wait for
lists to fill, and to shut down cleanly. It spreads over all the cores,
and learns to execute commands whose keys live on different shards. It
moves its values to disk, so it can store more data than fits in memory,
and keeps its background work from disturbing its users. Finally it
gets an HTTP interface for administration, replication to another server
and metrics. Each version is a complete program that you can build, run
and benchmark, and the book shows the parts that each chapter adds.

[Chapter](#ch:tutorial-introduction) starts with smaller programs, to give you a quick tour of
Seastar before we settle down to build Shoal. [Chapter](#ch:getting-started) then explains
how to get Seastar, and how to build and run a Seastar program of your
own.

## Exercises

1. Find out how many cores your computer has, with `nproc` or `lscpu`.
   Then run `lscpu -e`, which lists every core with its caches and
   maximum frequency. Are all your cores the same? Many laptops, and some
   servers, mix fast cores with slower, more power-efficient ones. What
   might that mean for a design in which every shard does the same work?
   ([Chapter](#ch:deploying-and-tuning) returns to this question.)

2. Write a small C++ program that starts one thread per core, and has
   each thread increment a shared `std::atomic<long>` a hundred million
   times. Then change it so that each thread increments its own
   `std::atomic<long>`, each in a separate cache line (put each counter
   in a struct declared `alignas(64)`). Finally, put the per-thread
   counters next to each other in an array, so they share cache lines.
   Measure all three versions with one thread and with all your cores,
   and explain the results. What happens if you make the per-thread
   counters plain `long` variables instead of atomic ones, and why?

3. Install Valkey (`sudo dnf install valkey` on Fedora), and run
   `valkey-server --save ''` (the option turns off periodic snapshots,
   which would disturb the measurement). In another window, load it with
   `valkey-benchmark -t get -P 16 --threads 4 -n 100000000 -q`. The large
   number of requests should keep it running for at least half a minute;
   if it finishes sooner, increase it. While it runs, watch the server
   with `top`: press `H`
   to see individual threads, and `1` to see each core. How many cores
   does the server use? What limits its throughput? Then load it harder,
   with `-P 64 -c 200`. What happens to the throughput, and to the
   latency that `valkey-benchmark` reports? Keep your numbers; we'll
   compare them with Shoal's later.

4. Estimate the per-request budget, in cycles, for a server that must
   answer ten million requests per second on an 8-core machine running
   at 2.5 GHz. How many cache misses could each request afford?
