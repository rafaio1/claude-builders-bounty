{-# LANGUAGE OverloadedStrings #-}
module Network.HTTP.Types where

import Data.ByteString (ByteString)

data Status = Status {
    statusCode    :: Int,
    statusMessage :: ByteString
} deriving (Show, Eq)

status200 :: Status
status200 = Status 200 "OK"

status400 :: Status
status400 = Status 400 "Bad Request"

status404 :: Status
status404 = Status 404 "Not Found"

status405 :: Status
status405 = Status 405 "Method Not Allowed"

status418 :: Status
status418 = Status 418 "I'm a teapot"

status500 :: Status
status500 = Status 500 "Internal Server Error"

status503 :: Status
status503 = Status 503 "Service Unavailable"

type HeaderName = ByteString

hContentType :: HeaderName
hContentType = "Content-Type"

hContentLength :: HeaderName
hContentLength = "Content-Length"
