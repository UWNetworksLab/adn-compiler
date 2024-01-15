local socket = require("socket")
math.randomseed(socket.gettime()*1000)
math.random();

local function randomString(length)
    local str = ""
    for i = 1, length do
        str = str .. string.char(math.random(97, 122)) -- Generates a random lowercase letter
    end
    return str
end

local function req_random()
    local method = "GET"
    local str = randomString(100)
    local path = "http://10.96.88.88:8080/ping-echo?body=" .. str
    local headers = {}
    return wrk.format(method, path, headers, str)
end

local function req_test()
    local method = "GET"
    local path = "http://10.96.88.88:8080/ping-echo?body=test"
    local headers = {}
    return wrk.format(method, path, headers, str)
end

request = function()

    local req_rand_ratio  = 0.95
    -- local req_test_ratio   = 1 - req_rand_ratio

    local coin = math.random()
    if coin < req_rand_ratio then
        return req_random()
    else
        return req_test()
    end
end
