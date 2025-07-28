
from tempfile import NamedTemporaryFile
from io import BytesIO
import subprocess
import os

import requests
from PIL import Image

from youtube import YOUTUBE

default_path='C:\\Users\\DELL\\Desktop\\side project'
ffmpeg_path='C:\\ffmpeg\\ffmpeg-2024-03-11-git-3d1860ec8d-full_build\\bin\\ffmpeg.exe'

def clear_screen():
    os.system('cls')


def custom_progress_bar(current, total, length=60)->str:
    progress = current / total
    blocks_completed = int(progress * length)
    bar = '[' + '=' * blocks_completed + '>' + ' ' * (length - blocks_completed) + ']'
    percentage = '{:.0%}'.format(progress)
    print('\r' + bar + ' ' + percentage, end='', flush=True)


def _valid_name(name:str)->str:
    return ''.join(a if not a in '<>:"/\\|?*' else '_' for a in name)

def valid_path_name(dir_path,name:str)->str:
    name,extention=_valid_name(name).rsplit('.', 1)
    number=1
    extra=''
    while os.path.exists(dir_path+'\\'+name+extra+'.'+extention):
        extra=f'({number})'
        number+=1
    return dir_path+'\\'+name+extra+'.'+extention


def valid_dir_name(dir_path:str,name:str)->str:
    name=_valid_name(name)
    extra=''
    number=1
    while os.path.exists(dir_path+'\\'+name+extra):
        extra=f'({number})'
        number+=1
    return dir_path+'\\'+name+extra

def crop_center_square(image_path)->None:
    with open(image_path, 'rb') as f:
        image_data = f.read()
    img = Image.open(BytesIO(image_data))
    width, height = img.size
    size = min(width, height)
    left = (width - size) // 2
    top = (height - size) // 2
    right = left + size
    bottom = top + size
    img = img.crop((left, top, right, bottom))
    img.save(image_path)
    
def get_size(content_length)->str:
    content_length=int(content_length)
    if content_length >= 1073741824:
        return f"{content_length / 1073741824:.2f} GB"
    elif content_length >= 1048576:
        return f"{content_length / 1048576:.2f} MB"
    elif content_length >= 1024:
        return f"{content_length / 1024:.2f} KB"
    else:
        return f"{content_length} bytes"
    
def sec_to_min_to_hours(sec)->str:
    min=float(sec)/60
    if min<60:time='%.2f min'%min
    else:time='%.2f hours'%(float(min)/60)
    return time

def add_audio_to_video(video_path, audio_path,ffmpeg_path,output_path):
    command = [ffmpeg_path,'-i', video_path,'-i', audio_path,'-c:v', 'copy','-c:a', 'aac','-strict', 'experimental',output_path]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
def convert_audio(input_file, output_file, ffmpeg_path):
    command = [ffmpeg_path, '-i', input_file, '-codec:a', 'libmp3lame', output_file]
    subprocess.run(command,stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def add_cover_in_music(audio_file_path:str, title:str, artist:str, cover_photo_url:str,output_path:str,ffmpeg_path:str):
    temp_file=NamedTemporaryFile(delete=False,suffix='.jpeg')
    download_file_with_resume(cover_photo_url,temp_file.name)
    crop_center_square(temp_file.name)
    comand=[ffmpeg_path, '-i', audio_file_path, '-i', temp_file.name,'-c','copy', '-map', '0', '-map', '1', '-metadata', f'title={title}', '-metadata', f'artist={artist}', output_path]
    subprocess.call(comand,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    temp_file.close()
    os.unlink(temp_file.name)
    
    
def _add_cover_and_meta_data(input_data,output_path,ffmpeg_path,title, artist, cover_photo_url):
    temp_file='output.mp3'
    convert_audio(input_data,temp_file,ffmpeg_path)
    add_cover_in_music(temp_file,title,artist,cover_photo_url,output_path,ffmpeg_path)
    os.unlink(temp_file)
    

def download_file_with_resume(url, filename, retry=1,downloaded_bytes=0): 
    try:
        headers = {'Range': f'bytes={downloaded_bytes}-'}
        response = requests.get(url, headers=headers, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        custom_progress_bar(downloaded_bytes, total_size)
        with open(filename, 'ab') as f:
            for chunk in response.iter_content(chunk_size=4096):
                if not chunk: continue
                f.write(chunk)
                downloaded_bytes += len(chunk)
                custom_progress_bar(downloaded_bytes, total_size)
        print()
        return True
    except Exception:return None


def handeking_error_while_downloading_music(dict1,quality:str,mime_type,output_path,attempt_to_download=1):
    quality=quality if quality.isdigit() else '3'
    for _ in range(attempt_to_download):
        link_audio=get_audio_link_quality(dict1,quality,mime_type)[0]
        response=download_file_with_resume(link_audio,output_path)
        if response:return True
        else:
            mime_type = 'opus' if mime_type=='mp3' else 'mp3' if 3-attempt_to_download==0 else'opus'
            quality = '1' if int(quality)>3 else '2'if quality !='2' else '3'
            with open(output_path,'wb')as f:f.write(b'')
    return False


def get_video_info(youtube_onj:YOUTUBE)->dict|None:
    streaming_data=youtube_onj.YouTube.streaming_data()
    if streaming_data is None:return None
    if streaming_data['formats'][0].get('url',None) is None:return None
    
    dict1={'video':{'audio_aviable':{},'mp4':{},'webm':{}},'music':{'mp3':{},'opus':{}}}
     
    for data in streaming_data['formats']:
        try:size=data['contentLength']
        except Exception:size=data['bitrate']*(int(data['approxDurationMs'])/10000)
        dict1['video']['audio_aviable'].update({data['qualityLabel']:(data['url'],size)})
    
    for data in streaming_data['adaptiveFormats']:
        mimetype=data['mimeType']
        if 'video/mp4' in mimetype:
            dict1['video']['mp4'].update({data['qualityLabel']:(data['url'],data['contentLength'])})
        elif 'video/webm' in mimetype:
            dict1['video']['webm'].update({data['qualityLabel']:(data['url'],data['contentLength'])})
        elif 'audio/mp4' in mimetype:
            dict1['music']['mp3'].update({data['contentLength']:(data['url'],data['audioQuality'])})
        elif 'audio/webm':
            dict1['music']['opus'].update({data['contentLength']:(data['url'],data['audioQuality'])})
    return dict1

def get_video_link_by_resulation(dict1,resulation,mime_type='mp4')->tuple|None:
    list_of_resulation=('2160p60','2160p','1440p60','1440p','1080p60','1080p','720p60','720p','480p60','480p','360p','240p','144p')
    mime_type='mp4'if mime_type not in ('mp4','webm') else mime_type
    resulation='360p' if resulation not in list_of_resulation else resulation
   
    mime_type = mime_type if dict1['video'].get(mime_type) is not None else 'mp4' if mime_type == 'webm' else 'webm'
    
    if dict1['video'][mime_type]is None:
        if dict1['video']['audio_aviable'] is None:return None
        else:mime_type='mp4';resulation='360p'
    
    if mime_type=='mp4' and (resulation=='360p' or resulation=='720p'):
        data=dict1['video']['audio_aviable'].get(resulation)
        if data is not None:return data,True,resulation,mime_type
    
    for i in (resulation+'60',resulation):
        data=dict1['video'][mime_type].get(i)
        if data is not None:return data,False,i,mime_type
    list_of_resulation=list_of_resulation[list_of_resulation.index(resulation):]
    for i in list_of_resulation:
        data=dict1['video'][mime_type].get(i)
        if data is not None:return data,False,i,mime_type
    return None

def get_audio_link_quality(dict1,quality:str,mime_type)->tuple|None:
    quality_list=('1','2','3')
    quality='3' if quality not in quality_list else quality
    mime_type='mp3' if mime_type not in ('mp3','opus') else mime_type
   
    mime_type = 'opus' if mime_type == 'mp3' and mime_type not in dict1['music'] else 'mp3'
    
    audio_data = dict1['music'].get(mime_type)
    if audio_data:
        quality_levels = sorted(map(int, audio_data.keys()))
        
        if quality == '1':
            return audio_data[str(quality_levels[0])]
        if quality == '2':
            return audio_data[str(quality_levels[len(quality_levels) // 2])]
        if quality == '3':
            return audio_data[str(quality_levels[-1])]
    return None


def getting_video_info_youtube(video:bool)->tuple[dict,str,str,str]|tuple[list,str]|None:
    clear_screen()
    link=input("Enter the link to download (n to exit): ")
    if link =='n':return 'going back'
    youtube_object=YOUTUBE(link)
    
    if video:
        dict1=get_video_info(youtube_onj=youtube_object)
        
        if dict1 is None:
            _=input("Error collecting data. Press enter to continue.")
            return None
        
        print('=' * 60)
        print(f'Video found: {youtube_object.YouTube.title()}')
        print(f'Length: {sec_to_min_to_hours(youtube_object.YouTube.length_sec())}')
        print('=' * 60)
        return (dict1,
                youtube_object.YouTube.title(),
                youtube_object.YouTube.artist_name(),
                youtube_object.YouTube.thumbnail(5))
    else:
        get_all_video_id=youtube_object.playlist.extract_video_id()
        
        if get_all_video_id is None:
            _=input("Error getting playlist data. Press enter to continue.")
            return None
        
        print('=' * 60)
        print(f'Playlist name: {youtube_object.playlist.get_title_of_playlist()}')
        print(f'Total videos: {youtube_object.playlist.get_size_of_playlist()}')
        print('=' * 60)
        print("Note: Selecting lower resolution may cause errors")
        
        return (
            get_all_video_id,
            youtube_object.playlist.get_title_of_playlist())


def audio_downloader_youtube(link_of_music:str, path_to_save:str, ffmpeg_path:str, title_video:str , artist_name:str , thumbnail_link:str)->None:
    with NamedTemporaryFile(delete=False , dir=default_path) as temp_audi_path:
        response=download_file_with_resume(link_of_music,temp_audi_path.name)
    
    if response:
        print("Adding cover image and metadata...")
        _add_cover_and_meta_data(temp_audi_path.name,path_to_save,ffmpeg_path,_valid_name(title_video),artist_name,thumbnail_link)
        print(f"File saved to: {path_to_save}")
    else:
        print("Error downloading file. Try a different quality.")
    os.unlink(temp_audi_path.name)
    
def video_downloader_youtube(video_staus_if_audio:bool,link_video:str,dict1:dict,attempt_to_download:int,output_path:str,ffmpeg_path:str)->bool:
    print("Video downloading started...")
    if not video_staus_if_audio:
        with NamedTemporaryFile(delete=False,dir=default_path) as video_file:
            response=download_file_with_resume(link_video,video_file.name)
        if not response:return False
        
        print("Audio downloading started...")
        with NamedTemporaryFile(delete=False,dir=default_path) as audio_file:
            music=handeking_error_while_downloading_music(dict1,'3','mp3',audio_file.name,attempt_to_download)
        
        if music:
            add_audio_to_video(video_file.name,audio_file.name,ffmpeg_path,output_path)
        else:
            print("Failed to add audio to the video")
        os.unlink(audio_file.name)
        os.unlink(video_file.name)
    else:
        response=download_file_with_resume(link_video,output_path)
        if not response:
            os.unlink(output_path)
            return False
    return True



def youtube_dowloader():
    def youtube_audio_downloader():
        data=getting_video_info_youtube(video=True)
        if data=='going back':return None
        dict1,title_video,artist_name,thumbnail_link=data
        
        useful_data=[]
        for num,data in enumerate(dict1['music']['mp3'].items(),start=1):
            print(f"[{num}] {data[1][1]} - {get_size(data[0])}")
            useful_data.append(data[1][0])
        for num,data in enumerate(dict1['music']['opus'].items(),start=num+1):
            print(f"[{num}] {data[1][1]} - {get_size(data[0])}")
            useful_data.append(data[1][0])
        
        path=valid_path_name(default_path,title_video+'.mp3')
        while not (resulation:=input("Enter quality number to download: ")).isdigit() or not 1<=int(resulation)<=num:
            print("Please enter a valid option")
        audio_downloader_youtube(useful_data[int(resulation)-1],path,ffmpeg_path,title_video,artist_name,thumbnail_link) 
        
    def video_downloadedr():
        data=getting_video_info_youtube(video=True)
        if data=='going back':return None
        dict1, video_title, artist,thumbnail_link=data
        useful_data=[]
        
        print("\nAvailable formats with audio:")
        print("="*50)
        for num,items in enumerate(dict1['video']['audio_aviable'].items(),start=1):
            print(f"[{num}] {items[0]} - {get_size(items[1][1])}")
            useful_data.append([items[1][0],'.mp4',True])
        
        print("\nMP4 formats (no audio):")
        print("="*50)
        for num,items in enumerate(dict1['video']['mp4'].items(),start=num+1):
            print(f"[{num}] {items[0]} - {get_size(items[1][1])}")
            useful_data.append([items[1][0],'.mp4',False])
        
        print("\nWebM formats (no audio):")
        print("="*50)
        for num,items in enumerate(dict1['video']['webm'].items(),start=num+1):
            print(f"[{num}] {items[0]} - {get_size(items[1][1])}")
            useful_data.append([items[1][0],'.webm',False])
        print("\nNote: For formats without audio, we will try to add audio separately")
        
        while not (resulation:=input("\nEnter number to download: ")).isdigit() or not 1<=int(resulation)<=num:
            print("Please enter a valid option")
            
        path=valid_path_name(default_path,video_title+useful_data[int(resulation)-1][1])
        
        response=video_downloader_youtube(useful_data[int(resulation)-1][2],useful_data[int(resulation)-1][0],dict1,2,path,ffmpeg_path)
        if response:
            print(f"Download complete. Saved to: {path}")
        else:
            print("Error during download. Try a different resolution.")
        
        
    def playlist_video_downloader():
        data=getting_video_info_youtube(video=False)
        if data=='going back':return None
        get_all_video_id,title_playlist=data
        
        print("\nAvailable resolutions: 144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 2160p")
        while not (resulation:=input("Enter resolution: ")) in ('144p','240p','360p','480p','720p','1080p','1440p','2160p'):
            print("Please select a valid resolution from the list")
        
        playlist_saving_dir=valid_dir_name(default_path,title_playlist)
        os.mkdir(playlist_saving_dir)
        
        for num,id in enumerate(get_all_video_id,start=1):
            link=f'https://www.youtube.com/watch?v={id}'
            
            new_youtube_obj=YOUTUBE(link)
            dict1=get_video_info(new_youtube_obj)
            print("="*80)
            
            if dict1 is None:
                print(f"[{num}] Error downloading: {new_youtube_obj.YouTube.title()}")
                print(f"Link: {link}")
                continue
            
            output_path=valid_path_name(playlist_saving_dir,new_youtube_obj.YouTube.title()+'.mp4')
            data_got=get_video_link_by_resulation(dict1,resulation,'mp4')
            
            print(f"[{num}] Downloading: {new_youtube_obj.YouTube.title()}")
            print(f"Size: {get_size(data_got[0][1])} Resolution: {data_got[2]}")
            response=video_downloader_youtube(data_got[1],data_got[0][0],dict1,2,output_path,ffmpeg_path)
            
            if response:
                print(f"Download complete. Saved to: {output_path}")
            else:
                print("Error during download. Try a different resolution.")
            
    def playlist_audio_downloaderr():
        data=getting_video_info_youtube(video=False)
        if data=='going back':return None
        get_all_video_id,title_playlist=data
        
        print("\nSelect quality:")
        print("1. Lower quality")
        print("2. Medium quality")
        print("3. Higher quality")
        while not (quality:=input("Enter choice (1-3): ")) in ('1','2','3'):
            print("Please enter a valid option")
            
        playlist_saving_dir=valid_dir_name(default_path,title_playlist)
        os.mkdir(playlist_saving_dir)
        for num,id in enumerate(get_all_video_id,start=1):
            link=f'https://www.youtube.com/watch?v={id}'
            
            new_youtube_obj=YOUTUBE(link)
            dict1=get_video_info(new_youtube_obj)
            print("="*80)
            
            if dict1 is None:
                print(f"[{num}] Error downloading: {new_youtube_obj.YouTube.title()}")
                print(f"Link: {link}")
                continue
            
            output_path=valid_path_name(playlist_saving_dir,new_youtube_obj.YouTube.title()+'.mp3')
            link=get_audio_link_quality(dict1,quality,'mp3')[0]
            
            print(f"[{num}] Downloading: {new_youtube_obj.YouTube.title()}")
            audio_downloader_youtube(link,output_path,ffmpeg_path,new_youtube_obj.YouTube.title(),new_youtube_obj.YouTube.artist_name(),new_youtube_obj.YouTube.thumbnail(5))

    while True:
        clear_screen()
        print("YouTube Download Options:")
        print("1. Video download")
        print("2. Audio download")
        print("3. Playlist video download")
        print("4. Playlist audio download")
        print("5. Go back")
        response=input("Enter your choice (1-5): ")
        match response:
            case '1':video_downloadedr()
            case '2':youtube_audio_downloader()
            case '3':playlist_video_downloader()
            case '4':playlist_audio_downloaderr()
            case '5':break
            case _:_=input("Invalid choice. Press enter to continue.")
        _=input("Press enter to continue...")
def facebook_downloader():pass
def instagrama_downloader():pass
def pinterest_downloader():pass
def whatsapp_downloader():pass
def spotiy_downloader():pass
def other_downloader():pass
def setting():pass
def main():
    while True:
        clear_screen()
        print("Downloader Menu:")
        print("1. YouTube Downloader")
        print("2. Facebook Downloader")
        print("3. Instagram Downloader")
        print("4. Pinterest Downloader")
        print("5. WhatsApp Status Downloader")
        print("6. Spotify Audio Downloader")
        print("7. Other Downloads")
        print("8. Settings")
        print("9. Quit")
        print("="*40)
        response=input("Enter your choice (1-9): ")
        match response:
            case '1':youtube_dowloader()
            case '2':facebook_downloader()
            case '3':instagrama_downloader()
            case '4':pinterest_downloader()
            case '5':whatsapp_downloader()
            case '6':spotiy_downloader()
            case '7':other_downloader()
            case '8':setting()
            case '9':break
            case _:_=input("Invalid choice. Press enter to continue.")

if __name__=="__main__":
    main()