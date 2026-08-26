module Network.Wai.Handler.Warp where

import Network.Wai (Application, Response)
import Data.Text (Text)

type Port = Int
type HostPreference = String

data Settings = Settings {
    settingsPort :: Port,
    settingsHost :: HostPreference,
    settingsLogger :: Maybe (Text -> IO ())
}

defaultSettings :: Settings
defaultSettings = Settings 3000 "*" Nothing

setPort :: Port -> Settings -> Settings
setPort p s = s { settingsPort = p }

setHost :: HostPreference -> Settings -> Settings
setHost h s = s { settingsHost = h }

setLogger :: (Text -> IO ()) -> Settings -> Settings
setLogger l s = s { settingsLogger = Just l }

run :: Port -> Application -> IO ()
run _ _ = putStrLn "[Warp] Server would start here (stub)"

runSettings :: Settings -> Application -> IO ()
runSettings _ _ = putStrLn "[Warp] Server would start with settings (stub)"
