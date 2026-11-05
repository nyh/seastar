// Compile check for the code snippets in chapter 1.
#include <seastar/core/coroutine.hh>
#include <seastar/core/sharded.hh>
#include <seastar/core/iostream.hh>
#include <seastar/core/sstring.hh>
#include <seastar/net/api.hh>
#include <functional>
#include <optional>

using namespace seastar;

future<std::optional<sstring>> read_request(input_stream<char>& in);
future<sstring> execute(sstring request);

future<> handle_connection(connected_socket s) {
    auto in = s.input();
    auto out = s.output();
    while (auto request = co_await read_request(in)) {
        co_await out.write(co_await execute(*request));
        co_await out.flush();
    }
    co_await out.close();
}

struct store {
    size_t size() const;
    future<> stop();
};

future<size_t> count_keys(sharded<store>& db) {
    return db.map_reduce0([] (const store& s) { return s.size(); },
                          size_t(0), std::plus<>());
}
