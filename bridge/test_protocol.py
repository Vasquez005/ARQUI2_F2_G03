import unittest

from protocol import FrameStreamDecoder, encode_frame, parse_frame


class FrameStreamDecoderTests(unittest.TestCase):
    def test_reconstruye_frame_fragmentado(self):
        expected = encode_frame(
            "UNO_ENTRADA", 1, "EVT", "garita", "estado=iniciando;garita=entrada"
        )
        decoder = FrameStreamDecoder()

        self.assertEqual(decoder.feed(b"Firmware Version: 0x92\r\n<PORT"), [])
        self.assertEqual(decoder.feed(b"US|UNO_ENTRADA|1|EVT|garita|estado="), [])
        frames = decoder.feed(("iniciando;garita=entrada|7B>\r\n").encode())

        self.assertEqual(frames, [expected])
        self.assertEqual(parse_frame(frames[0]).src, "UNO_ENTRADA")

    def test_extrae_varios_frames_entre_logs(self):
        first = encode_frame("UNO_ENTRADA", 2, "HBT", "estado", "degradado=0")
        second = encode_frame("UNO_ENTRADA", 3, "EVT", "garita", "evento=rfid")
        decoder = FrameStreamDecoder()

        frames = decoder.feed(f"log libre\r\n{first}\r\notro log\r\n{second}\r\n".encode())

        self.assertEqual(frames, [first, second])

    def test_descarta_fragmentos_sin_inicio_de_frame(self):
        decoder = FrameStreamDecoder()
        self.assertEqual(decoder.feed(b"7B>\r\n62>\r\n"), [])
        valid = encode_frame("UNO_ENTRADA", 4, "HBT", "estado", "barra=cerrada")
        self.assertEqual(decoder.feed(valid.encode()), [valid])


if __name__ == "__main__":
    unittest.main()
