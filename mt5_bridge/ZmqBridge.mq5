//+------------------------------------------------------------------+
//| ZmqBridge.mq5 - ZeroMQ Bridge for Codex Ultra Trader             |
//+------------------------------------------------------------------+
#property copyright "Codex Orchestrator"
#property version   "1.00"
#property strict

input string ZmqAddress = "tcp://*:5555";
input int    ZmqTimeout = 5000;

// Simple ZMQ REP socket simulation via named pipes/files for Wine compatibility
// Since native ZMQ DLLs are complex in Wine, we use a file-based IPC fallback
string IPC_REQUEST  = "C:\\Temp\\zmq_req.json";
string IPC_RESPONSE = "C:\\Temp\\zmq_rep.json";

int OnInit() {
   Print("ZmqBridge initialized. Listening on file IPC: ", IPC_REQUEST);
   EventSetMillisecondTimer(100);
   return(INIT_SUCCEEDED);
}

void OnTimer() {
   if(FileIsExist(IPC_REQUEST)) {
      string request = "";
      int handle = FileOpen(IPC_REQUEST, FILE_READ|FILE_TXT|FILE_ANSI);
      if(handle != INVALID_HANDLE) {
         request = FileReadString(handle);
         FileClose(handle);
         FileDelete(IPC_REQUEST);
         
         string response = ProcessRequest(request);
         
         handle = FileOpen(IPC_RESPONSE, FILE_WRITE|FILE_TXT|FILE_ANSI);
         if(handle != INVALID_HANDLE) {
            FileWriteString(handle, response);
            FileClose(handle);
         }
      }
   }
}

string ProcessRequest(string json) {
   // Parse simple JSON commands: {"cmd":"balance"}, {"cmd":"trade","symbol":"EURUSD","type":"buy","lot":0.01}
   if(StringFind(json, "\"balance\"") >= 0) {
      double bal = AccountInfoDouble(ACCOUNT_BALANCE);
      double eq  = AccountInfoDouble(ACCOUNT_EQUITY);
      return StringFormat("{\"balance\":%.2f,\"equity\":%.2f,\"leverage\":%d}", bal, eq, AccountInfoInteger(ACCOUNT_LEVERAGE));
   }
   if(StringFind(json, "\"news\"") >= 0) {
      // Return last 5 news headlines from MT5 Economic Calendar
      MqlCalendarEvent events[];
      datetime from = TimeCurrent() - 86400;
      datetime to   = TimeCurrent() + 86400;
      int count = CalendarEventHistory(events, from, to);
      string news = "[";
      for(int i=0; i<MathMin(count,5); i++) {
         if(i>0) news += ",";
         news += StringFormat("{\"time\":\"%s\",\"event\":\"%s\",\"impact\":%d}", 
                  TimeToString(events[i].time), events[i].name, events[i].impact);
      }
      news += "]";
      return news;
   }
   if(StringFind(json, "\"trade\"") >= 0) {
      // Execute trade - simplified parser
      MqlTradeRequest req = {};
      MqlTradeResult res = {};
      req.action = TRADE_ACTION_DEAL;
      req.magic = 123456;
      req.deviation = 10;
      req.type_filling = ORDER_FILLING_IOC;
      
      // Parse symbol, type, lot from JSON (basic extraction)
      // In production, use proper JSON library
      if(StringFind(json, "\"buy\"") >= 0) req.type = ORDER_TYPE_BUY;
      else req.type = ORDER_TYPE_SELL;
      
      // Extract lot size
      int lotPos = StringFind(json, "\"lot\"");
      if(lotPos >= 0) {
         string lotStr = StringSubstr(json, lotPos+6, 10);
         req.volume = StringToDouble(lotStr);
      } else {
         req.volume = 0.01; // Minimum safe lot for Fase 1
      }
      
      // Extract symbol
      int symPos = StringFind(json, "\"symbol\"");
      if(symPos >= 0) {
         int start = StringFind(json, ":", symPos) + 2;
         int end = StringFind(json, "\"", start);
         req.symbol = StringSubstr(json, start, end-start);
      } else {
         req.symbol = "EURUSD";
      }
      
      req.price = SymbolInfoDouble(req.symbol, (req.type==ORDER_TYPE_BUY)?SYMBOL_ASK:SYMBOL_BID);
      
      if(OrderSend(req, res)) {
         return StringFormat("{\"status\":\"ok\",\"ticket\":%d,\"price\":%.5f}", res.order, res.price);
      } else {
         return StringFormat("{\"status\":\"error\",\"code\":%d,\"msg\":\"%s\"}", res.retcode, GetRetcodeDescription(res.retcode));
      }
   }
   return "{\"status\":\"unknown_command\"}";
}

void OnDeinit(const int reason) {
   EventKillTimer();
   Print("ZmqBridge stopped.");
}
