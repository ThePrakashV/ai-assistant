import sounddevice as sd

print("Available audio devices:\n")
print(sd.query_devices())
print("\nDefault (input, output):", sd.default.device)