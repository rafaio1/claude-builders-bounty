module Network.Wai.Logger where

import Data.Text (Text)

withStdoutLogger :: ((Text -> IO ()) -> IO a) -> IO a
withStdoutLogger f = f (\msg -> putStrLn ("[log] " ++ show msg))
