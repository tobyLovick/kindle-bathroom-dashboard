--[[
Bathroom dashboard plugin for KOReader.

Two buttons: log weight or log night mood (0.5-5 stars).
Either action POSTs to the bathroom-dashboard server (hosted on your own
always-on machine, over Tailscale Funnel), then re-fetches the rendered
PNG and overwrites the file KOReader's own screensaver setting already
points at -- so the next time the Kindle sleeps, the screensaver shows
the fresh chart.

CONFIDENCE NOTE (so debugging starts in the right place, not everywhere):
- WidgetContainer, UIManager:show/close, ButtonTable, InputDialog
  (input_type="number", getInputValue()) are patterns confirmed against
  KOReader's actual source during research for this project.
- The `json` and `socket.http`/`ssl.https` require paths below are
  standard KOReader/Lua conventions, NOT individually verified against
  this exact KOReader build. If something breaks on first run, check
  these requires and the exact module paths first.
--]]

local WidgetContainer = require("ui/widget/container/widgetcontainer")
local UIManager = require("ui/uimanager")
local ButtonTable = require("ui/widget/buttontable")
local InputDialog = require("ui/widget/inputdialog")
local InfoMessage = require("ui/widget/infomessage")
local ImageWidget = require("ui/widget/imagewidget")
local OverlapGroup = require("ui/widget/overlapgroup")
local BottomContainer = require("ui/widget/container/bottomcontainer")
local LeftContainer = require("ui/widget/container/leftcontainer")
local RightContainer = require("ui/widget/container/rightcontainer")
local Button = require("ui/widget/button")
local Geom = require("ui/geometry")
local Screen = require("device").screen
local ltn12 = require("ltn12")
local https = require("ssl.https")
local json = require("json")

local SERVER = "https://YOUR-DEVICE.YOUR-TAILNET.ts.net"  -- set this to your own Tailscale Funnel URL (see README)
local TOKEN = "REPLACE_WITH_YOUR_OWN_BEARER_TOKEN"  -- generate your own, see README
-- Must match whatever path KOReader's own Screensaver menu is already
-- pointed at (set manually once via Menu -> gear icon -> Screensaver).
local SCREENSAVER_PATH = "/mnt/us/screensaver_test/screensaver_test.png"

local BathDash = WidgetContainer:extend{
    name = "bathdash",
}

local function http_request(method, path, body_table)
    local body = body_table and json.encode(body_table) or nil
    local response_chunks = {}
    local request_source = body and ltn12.source.string(body) or nil
    local headers = {
        ["Authorization"] = "Bearer " .. TOKEN,
    }
    if body then
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = tostring(#body)
    end
    local ok, code = https.request{
        url = SERVER .. path,
        method = method,
        headers = headers,
        source = request_source,
        sink = ltn12.sink.table(response_chunks),
    }
    return ok, code, table.concat(response_chunks)
end

local function refresh_screensaver()
    local response_chunks = {}
    local ok, code = https.request{
        url = SERVER .. "/dashboard.png",
        method = "GET",
        headers = { ["Authorization"] = "Bearer " .. TOKEN },
        sink = ltn12.sink.table(response_chunks),
    }
    if ok and code == 200 then
        local f = io.open(SCREENSAVER_PATH, "wb")
        if f then
            f:write(table.concat(response_chunks))
            f:close()
            return true
        end
    end
    return false
end

local function notify(text)
    UIManager:show(InfoMessage:new{ text = text, timeout = 2 })
end

function BathDash:init()
    self.ui.menu:registerToMainMenu(self)
    -- NOT auto-shown on startup anymore -- the previous version had no
    -- way to dismiss the screen it force-showed, which trapped the
    -- device. Only opens now via the menu entry below, with an explicit
    -- Close button on every screen.
end

function BathDash:addToMainMenu(menu_items)
    menu_items.bathdash = {
        text = "Bathroom Dashboard",
        callback = function() self:showMain() end,
    }
end

function BathDash:showMain()
    local screen_w, screen_h = Screen:getWidth(), Screen:getHeight()
    local full_dimen = Geom:new{ w = screen_w, h = screen_h }

    -- The live dashboard chart as the actual background of this screen,
    -- not KOReader's normal view showing through underneath -- same
    -- image file the screensaver uses, so this screen already looks
    -- like a preview of what sleeping will show.
    local background = ImageWidget:new{
        file = SCREENSAVER_PATH,
        width = screen_w,
        height = screen_h,
    }

    local btn_weight = Button:new{
        text = "Log weight",
        callback = function() self:showWeightEntry() end,
    }
    local btn_mood = Button:new{
        text = "Log mood",
        callback = function() self:showMoodEntry() end,
    }
    local btn_close = Button:new{
        text = "x",
        callback = function()
            if self.main_widget then
                UIManager:close(self.main_widget)
                self.main_widget = nil
            end
        end,
    }

    local bottom_left = BottomContainer:new{
        dimen = full_dimen,
        LeftContainer:new{
            dimen = Geom:new{ w = screen_w, h = btn_weight:getSize().h },
            btn_weight,
        },
    }
    local bottom_right = BottomContainer:new{
        dimen = full_dimen,
        RightContainer:new{
            dimen = Geom:new{ w = screen_w, h = btn_mood:getSize().h },
            btn_mood,
        },
    }
    local top_right_close = RightContainer:new{
        dimen = Geom:new{ w = screen_w, h = btn_close:getSize().h },
        btn_close,
    }

    if self.main_widget then
        UIManager:close(self.main_widget)
    end
    self.main_widget = OverlapGroup:new{
        dimen = full_dimen,
        allow_mirroring = false,
        background,
        bottom_left,
        bottom_right,
        top_right_close,
    }
    UIManager:show(self.main_widget, "full")
end

function BathDash:showWeightEntry()
    self.weight_dialog = InputDialog:new{
        title = "Weight (kg)",
        input_type = "number",
        buttons = {
            {
                {
                    text = "Cancel",
                    id = "close",
                    callback = function()
                        UIManager:close(self.weight_dialog)
                    end,
                },
                {
                    text = "Save",
                    is_enter_default = true,
                    callback = function()
                        local value = tonumber(self.weight_dialog:getInputValue())
                        UIManager:close(self.weight_dialog)
                        if value then
                            self:submitWeight(value)
                        else
                            notify("Not a number, try again")
                        end
                    end,
                },
            },
        },
    }
    UIManager:show(self.weight_dialog, "full")
    self.weight_dialog:onShowKeyboard()
end

function BathDash:submitWeight(value)
    notify("Saving...")
    local ok, code = http_request("POST", "/weight", { value = value })
    if ok and code == 200 then
        notify("Weight saved: " .. tostring(value) .. " kg")
        refresh_screensaver()
    else
        notify("Failed to save (check WiFi): " .. tostring(code))
    end
    self:showMain()
end

function BathDash:showMoodEntry()
    -- 10 buttons in half-star steps (0.5 .. 5.0), ALL in a single flat
    -- row -- the previous 2-row nested layout was an unverified guess at
    -- ButtonTable's structure and apparently only the last row actually
    -- rendered/registered. One row removes that ambiguity entirely.
    local row = {}
    for i = 1, 10 do
        local value = i * 0.5
        table.insert(row, {
            text = tostring(value),
            callback = function() self:submitMood(value) end,
        })
    end
    -- Cancel appended to the SAME flat row, not a second row -- a second
    -- row is exactly the structure that silently failed to render before.
    table.insert(row, {
        text = "Cancel",
        callback = function()
            if self.mood_widget then
                UIManager:close(self.mood_widget)
                self.mood_widget = nil
            end
            self:showMain()
        end,
    })
    if self.mood_widget then
        UIManager:close(self.mood_widget)
    end
    self.mood_widget = ButtonTable:new{
        buttons = { row },
        width = Screen:getWidth() * 0.95,
    }
    UIManager:show(self.mood_widget, "full")
end

function BathDash:submitMood(value)
    if self.mood_widget then
        UIManager:close(self.mood_widget)
    end
    notify("Saving...")
    local ok, code = http_request("POST", "/mood", { value = value })
    if ok and code == 200 then
        notify("Mood saved: " .. tostring(value) .. " stars")
        refresh_screensaver()
    else
        notify("Failed to save (check WiFi): " .. tostring(code))
    end
    self:showMain()
end

return BathDash
