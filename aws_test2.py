import streamlit as st
import requests
import json
import boto3
import random
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.units import inch
import os

# DynamoDB 및 S3 클라이언트 생성
dynamodb = boto3.resource('dynamodb', region_name='ap-southeast-1')
table = dynamodb.Table('test_team_1')
s3 = boto3.client('s3')
bucket_name = 'wsu-pbl-team-1'
# Lambda URL
lambda_url = "https://wnldrpj3tcxuhhgq2kr3afyzya0gbkps.lambda-url.ap-southeast-1.on.aws/"
# 고유한 ID를 생성하는 함수
def generate_unique_id():
    return random.randint(1, 255)
    
# 한글 폰트 설정 
font_path = "./NanumGothic.ttf"  # 한글 폰트 경로 설정
pdfmetrics.registerFont(TTFont('NanumGothic', font_path))

# 레시피 PDF 생성 함수
def create_pdf(recipe_name, ingredients, instructions):
    pdf_output = f"{recipe_name}.pdf"
    c = canvas.Canvas(pdf_output, pagesize=A4)

    # 한글 폰트 설정
    c.setFont("NanumGothic", 16)

    # 제목
    c.drawString(100, 800, recipe_name)

    # 재료 목록
    c.setFont("NanumGothic", 12)
    c.drawString(100, 780, "Ingredients:")
    y_position = 760
    for ingredient in ingredients:
        c.drawString(120, y_position, ingredient)
        y_position -= 20

    # 조리법
    c.setFont("NanumGothic", 10)
    c.drawString(100, y_position - 20, "Instructions:")
    y_position -= 40
    text = c.beginText(120, y_position)
    text.textLines(instructions)
    c.drawText(text)

    c.showPage()
    c.save()
    
    return pdf_output

# PDF 파일을 S3에 업로드하는 함수
def upload_to_s3(file_name, bucket_name):
    with open(file_name, 'rb') as file:
        s3.upload_fileobj(file, bucket_name, file_name)
    s3_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
    return s3_url
# 레시피 저장 함수 (user_name 포함)
def save_final_recipe(user_name, recipe_id, recipe_name, ingredients, instructions):
    table.put_item(
        Item={
            'user_name': user_name,  # 사용자 이름 저장
            '255': recipe_id,
            'RecipeName': recipe_name,
            'Ingredients': ingredients,
            'Instructions': instructions
        }
    )
    st.success(f"레시피 '{recipe_name}'이(가) 성공적으로 저장되었습니다.")
# 특정 사용자의 레시피 목록을 가져오는 함수
def get_user_recipes(user_name):
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('user_name').eq(user_name)
    )
    items = response.get('Items', [])
    return items
# 레시피 불러오기 함수
def get_recipe_by_name(recipe_name, user_name):
    # DynamoDB에서 user_name과 recipe_name이 일치하는 레시피를 검색
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('user_name').eq(user_name) &
                         boto3.dynamodb.conditions.Attr('RecipeName').eq(recipe_name)
    )
    items = response.get('Items', [])
    # 결과가 있으면 재료와 조리법을 반환
    if items:
        recipe = items[0]  # 첫 번째 항목을 가져옴
        return recipe['Ingredients'], recipe['Instructions']
    else:
        st.error(f"레시피 '{recipe_name}'을(를) 찾을 수 없습니다.")
        return None, None
# 사용자 이름 입력 칸
st.title("요리 레시피 추천 챗봇")
user_name = st.text_input("이름을 입력해주세요", "")
# 사용자 이름이 입력되면 챗봇 인터페이스 표시
if user_name:
    st.write(f"환영합니다, {user_name}님!")
    # 초기 상태 설정
    if 'responses' not in st.session_state:
        st.session_state.responses = {
            'button1': None,
            'button2': None,
            'button3': None,
            'button4': None,
            'button5': None,
            'recipes': []  # 사용자의 레시피 목록을 저장
        }
    # 저장된 사용자 레시피 목록 불러오기
    user_recipes = get_user_recipes(user_name)
    if user_recipes:
        st.session_state.responses['recipes'] = [recipe['RecipeName'] for recipe in user_recipes]
    # 1. 요리명 입력 후 재료 목록 받기
    recipe_name = st.text_input("요리명을 입력하세요", "")
    if st.button("재료 목록 받기"):
        if recipe_name:
            payload = {
                "message": f"'{recipe_name}'을(를) 만들기 위해 필요한 재료 목록을 알려주세요. 수량에서 엑체는 ml도 함께 알려주세요. 대답 형식=재료 목록 : 재료이름(필요한 양), 재료이름(필요한 양), 한줄로 출력"
            }
            response = requests.post(lambda_url, json=payload)
            if response.status_code == 200:
                result = json.loads(response.content)
                st.session_state.responses['button1'] = result['response']
            else:
                st.write(f"에러 발생: {response.status_code}")
        else:
            st.write("요리명을 입력해주세요.")
    if st.session_state.responses.get('button1') is not None:
        st.write("Claude의 답변:")
        st.success(st.session_state.responses['button1'])
    # 2. 부족한 재료 입력 후 대체 재료 받기
    ingredient = st.text_input("부족한 재료를 입력하세요", "")
    if st.button("대체 재료 받기"):
        if ingredient and recipe_name:
            payload = {
                "message": f"""{recipe_name}을 만들기 위한 재료 중 {ingredient}'이(가) 없을 경우 대체 가능한 재료나 맛을 낼 수 있는 재료을 알려주세요.
                수량에서 엑체는 ml도 함께 알려주세요.
                대답 형식= 대체 재료 목록, 원래 재료 목록"""
            }
            response = requests.post(lambda_url, json=payload)
            if response.status_code == 200:
                result = json.loads(response.content)
                st.session_state.responses['button2'] = result['response']
            else:
                st.write(f"에러 발생: {response.status_code}")
        else:
            st.write("요리명과 부족한 재료를 입력해주세요.")
    if st.session_state.responses.get('button2') is not None:
        st.write("Claude의 답변:")
        st.success(st.session_state.responses['button2'])
    # 3. 최종 재료 입력 후 레시피 받기
    final_ingredients = st.text_input("최종 재료 목록을 입력하세요 (쉼표로 구분)", "")
    if st.button("레시피 받기"):
        if final_ingredients and recipe_name:
            payload = {
                "message": f"이 재료들로 만들 수 있는 {recipe_name} 조리 방법을 간단하고 명료하게 제공해 주세요: {final_ingredients}."
            }
            response = requests.post(lambda_url, json=payload)
            if response.status_code == 200:
                result = json.loads(response.content)
                st.session_state.responses['button3'] = result['response']
            else:
                st.write(f"에러 발생: {response.status_code}")
        else:
            st.write("최종 재료 목록을 입력해주세요.")
    if st.session_state.responses.get('button3') is not None:
        st.write("Claude의 답변:")
        st.success(st.session_state.responses['button3'])
    # 4. 레시피 저장 (user_name 포함)
    if st.button("레시피 저장"):
        if recipe_name and final_ingredients and st.session_state.responses.get('button3'):
            recipe_id = generate_unique_id()
            ingredients_list = final_ingredients.split(",")
            instructions = st.session_state.responses['button3']
            save_final_recipe(user_name, recipe_id, recipe_name, ingredients_list, instructions)
            # PDF 생성 및 S3에 업로드
            pdf_file = create_pdf(recipe_name, ingredients_list, instructions)
            s3_url = upload_to_s3(pdf_file, bucket_name)
            st.success(f"레시피 PDF가 S3에 저장되었습니다: {s3_url}")
            # 레시피 목록 업데이트
            st.session_state.responses['recipes'].append(recipe_name)
            st.session_state.responses['button4'] = True
        else:
            st.write("레시피 저장에 필요한 정보를 입력해주세요.")
    # 5. 저장된 레시피 목록을 버튼 형식으로 표시하고, 버튼 클릭 시 해당 레시피 내용 출력
    st.header("저장된 레시피 목록")
    if st.session_state.responses['recipes']:
        for index, recipe in enumerate(st.session_state.responses['recipes']):
            # 고유한 key 값을 할당하기 위해 enumerate의 index를 활용
            if st.button(recipe, key=f"recipe_button_{index}"):
                ingredients, instructions = get_recipe_by_name(recipe, user_name)
                if ingredients and instructions:
                    st.write(f"**재료**: {', '.join(ingredients)}")
                    st.write(f"**조리 방법**: {instructions}")
    else:
        st.write("저장된 레시피가 없습니다.")
