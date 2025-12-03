package jpamb.cases;

import jpamb.utils.*;
import static jpamb.utils.Tag.TagType.*;

public class HardFuzzer {
    // non trivial signed integer overflow
    @Case("(1) -> ok")
    @Case("(0) -> divide by zero")
    @Case("(-1) -> ok")
    public static void signedOverflow(int n) {
        int x = 456 / n;
        while (x != 0) { // n goes to Integer.MIN_VALUE and rolls over to Integer.MAX_VALUE (then hits 0)
            x--;
        }
    }

    // evaluated expressions that produce large numbers
    @Case("(0) -> ok")
    @Case("(16777216) -> assertion error")
    public static void bigEvaluatedNumber(int n) {
        if (n == 64 * 64 * 64 * 64) { // n == 16777216
            assert false;
        }
    }

    // Array with specific ordering
    @Case("([I: ]) -> out of bounds")
    @Case("([I: 5, 4, 3, 2, 1]) -> assertion error")
    @Case("([I: 1, 2, 3, 4, 5]) -> ok")
    public static void arrayOrder(int[] arr) {
        boolean correct = false;
        for (int i = 0; i < 5; i += 1) {
            if (arr[i] == i + 1) {
                correct = true;
            } else {
                correct = false;
                break;
            }
        }
        assert correct;
    }

    // syntactic analysis doesn't find hexadecimal literals
    @Case("(0) -> ok")
    @Case("(-559038737) -> divide by zero")
    public static int hexMagicNumber(int n) {
        if (n == (int) 0xDEADBEEF) { // n = -559038737
            return 1 / 0;
        }
        return 1;
    }

    // central expansion doesn't reach extreme values quickly
    @Case("(0) -> ok")
    @Case("(2147483647) -> assertion error")
    public static void maxIntValue(int n) {
        if (n == Integer.MAX_VALUE) {
            assert false;
        }
    }

    // multiple parameters with specific combination - combinatorial explosion
    @Case("(0, 0, 0) -> ok")
    @Case("(12345, 67890, 11111) -> assertion error")
    public static void specificCombination(int a, int b, int c) {
        if (a == 12345 && b == 67890 && c == 11111) {
            assert false;
        }
    }
}