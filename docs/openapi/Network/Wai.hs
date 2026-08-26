module Network.Wai where

import Network.HTTP.Types (Status, HeaderName)
import Data.ByteString (ByteString)
import qualified Data.ByteString.Lazy as LBS
import Data.Text (Text)

type Application = Request -> (Response -> IO ResponseReceived) -> IO ResponseReceived

data Request = Request {
    requestMethod :: Method,
    pathInfo      :: [Text],
    queryString   :: [(ByteString, Maybe ByteString)]
} deriving (Show)

type Method = ByteString

type ResponseHeaders = [(HeaderName, ByteString)]

data Response = ResponseBuilder Status ResponseHeaders Builder
              | ResponseLBS Status ResponseHeaders LBS.ByteString
              deriving (Show)

newtype ResponseReceived = ResponseReceived ()

data Builder = Builder {
    buildBytes :: LBS.ByteString
} deriving (Show)

responseLBS :: Status -> ResponseHeaders -> LBS.ByteString -> Response
responseLBS = ResponseLBS

responseBuilder :: Status -> ResponseHeaders -> Builder -> Response
responseBuilder = ResponseBuilder
