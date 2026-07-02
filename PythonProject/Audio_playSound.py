import pygame

def run_complete_workflow(audio_path):

    if not pygame.mixer.get_init():
        pygame.mixer.init()

    pygame.mixer.music.load(audio_path)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
